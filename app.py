import os
import logging
import time
from datetime import datetime
from flask import Flask, request, jsonify, render_template
import py115
from py115.types import Credential

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# 환경 변수에서 Credential 정보 가져오기
uid = os.getenv('UID')
cid = os.getenv('CID')
seid = os.getenv('SEID')

# py115 초기화
credential = Credential(uid=uid, cid=cid, seid=seid)
cloud = py115.connect(credential=credential)
offline_service = cloud.offline()

# 작업 목록을 저장할 딕셔너리
tasks_created_times = {}
tasks_completed_times = {}

@app.route('/add_task', methods=['POST'])
def add_single_task():
    """
    단일 마그넷 URL을 받아서 오프라인 다운로드 작업을 추가하는 엔드포인트.
    """
    data = request.json
    magnet_url = data.get('magnet_url')
    logging.info(f"Received magnet URL: {magnet_url}")

    # 현재 시간을 기록 (작업 생성 시간)
    created_time = datetime.now()
    
    # 마그넷 URL을 통해 다운로드 작업 추가
    result = offline_service.add_url(magnet_url)
    logging.info(f"Task add result: {result}")

    # 추가된 작업의 세부 정보를 로그에 기록하고, 생성 시간을 저장
    for task in result:
        task_id = task.task_id
        tasks_created_times[task_id] = created_time  # 생성 시간을 저장
        logging.info(f"Task details: ID={task.task_id}, Name={task.name}, Status={task.status}, Created Time={created_time}, Percent={task.precent}, File ID={task.file_id}, Is Dir={task.file_is_dir}")
    
    return jsonify({'status': 'success', 'result': [task.task_id for task in result]})

@app.route('/')
def index():
    """
    기본 웹 페이지를 렌더링하는 엔드포인트.
    """
    return render_template('index.html')

@app.route('/tasks', methods=['GET'])
def list_tasks():
    """
    현재 오프라인 다운로드 작업 목록을 반환하는 엔드포인트.
    """
    tasks = []
    running_count = 0
    complete_count = 0
    for task in offline_service.list():
        status = 'Complete' if task.status.name == 'Complete' else 'Running'
        if status == 'Complete':
            complete_count += 1
        else:
            running_count += 1
        # 생성 시간을 기록한 시간 또는 기본 생성 시간으로 설정
        created_time = tasks_created_times.get(task.task_id, task.created_time)
        completed_time = tasks_completed_times.get(task.task_id, None)
        
        # 작업이 완료된 경우, 완료 시간을 기록
        if status == 'Complete' and task.task_id not in tasks_completed_times:
            completed_time = datetime.now()
            tasks_completed_times[task.task_id] = completed_time
        
        task_info = {
            'task_id': task.task_id,
            'name': task.name,
            'status': status,
            'created_time': created_time.strftime('%Y-%m-%d %H:%M:%S'),
            'completed_time': completed_time.strftime('%Y-%m-%d %H:%M:%S') if completed_time else '',
            'size': format_size(task.size),
            'percent': f'{task.precent:.1f}'
        }
        tasks.append(task_info)
    return jsonify({'tasks': tasks, 'running_count': running_count, 'complete_count': complete_count})

@app.route('/tasks/add', methods=['POST'])
def add_multiple_tasks():
    """
    여러 개의 마그넷 URL을 받아서 오프라인 다운로드 작업을 추가하는 엔드포인트.
    """
    data = request.json
    urls = data.get('urls')
    if not urls:
        return jsonify({'error': 'No URLs provided'}), 400

    # 마그넷 URL을 세미콜론(;)으로 구분
    url_list = urls.split(';')
    
    # 마그넷 URL을 통해 여러 개의 다운로드 작업 추가
    created_time = datetime.now()
    task_ids = []
    for url in url_list:
        result = offline_service.add_url(url)
        for task in result:
            task_ids.append(task.task_id)
            tasks_created_times[task.task_id] = created_time  # 생성 시간을 저장
            logging.info(f"Task added: ID={task.task_id}, Name={task.name}, Status={task.status}, Created Time={created_time}")
        time.sleep(3)  # 3초 간격으로 작업 추가
    return jsonify({'status': 'success', 'result': task_ids})

@app.route('/tasks/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    """
    특정 오프라인 다운로드 작업을 삭제하는 엔드포인트.
    """
    offline_service.delete(task_id)
    # 작업 생성 시간 정보도 삭제
    if task_id in tasks_created_times:
        del tasks_created_times[task_id]
    if task_id in tasks_completed_times:
        del tasks_completed_times[task_id]
    return jsonify({'status': 'deleted'})

@app.route('/tasks/clear_completed', methods=['POST'])
def clear_completed_tasks():
    """
    완료된 모든 오프라인 다운로드 작업을 삭제하는 엔드포인트.
    """
    offline_service.clear(status='Complete')
    # 완료된 작업의 생성 시간 정보도 삭제
    completed_tasks = [task.task_id for task in offline_service.list() if task.status.name == 'Complete']
    for task_id in completed_tasks:
        if task_id in tasks_created_times:
            del tasks_created_times[task_id]
        if task_id in tasks_completed_times:
            del tasks_completed_times[task_id]
    return jsonify({'status': 'completed tasks cleared'})

def format_size(size):
    """
    파일 크기를 적절한 단위로 변환하는 헬퍼 함수.
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)