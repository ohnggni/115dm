import os
import logging
import time
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from p115 import P115Client, P115Offline, P115FileSystem
import requests
import json

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# 환경변수에서 가져올 값들: 云下载 폴더 id, 115클라우드 cookie
default_download_path_id = os.getenv('C_FolderId')
cookie = os.getenv('P115_COOKIE')
uid = os.getenv('UID')

# 클라이언트 및 서비스 객체 생성
client = P115Client(cookie)
offline_service = P115Offline(client)
fs = P115FileSystem(client)

# 작업 목록을 저장할 딕셔너리
tasks_created_times = {}
tasks_completed_times = {}
task_folder_mapping = {} # 필요한 딕셔너리를 추가하여 wp_path_id를 저장합니다.
folder_id_to_name = {} # 폴더 ID와 이름 매핑을 저장할 딕셔너리

# 저장할 JSON 파일 경로 설정
TASK_TIMES_FILE = '/app/data/task_times.json'

# 파일에서 task_times를 로드하는 함수
def load_task_times():
    if os.path.exists(TASK_TIMES_FILE):
        with open(TASK_TIMES_FILE, 'r') as f:
            return json.load(f)
    return {}

# task_times를 파일에 저장하는 함수
def save_task_times(task_times):
    # 기존 파일의 내용을 로드합니다.
    existing_task_times = load_task_times()

    # 새로운 task_times를 기존 task_times에 병합합니다.
    for task_id, times in task_times.items():
        # 이미 존재하는 task_id에 대해서는 업데이트하지 않음
        if task_id not in existing_task_times:
            existing_task_times[task_id] = times

    # 병합된 내용을 다시 저장합니다.
    with open(TASK_TIMES_FILE, 'w') as f:
        json.dump(existing_task_times, f, indent=4, default=str)

# 특정 task_id를 파일에서 삭제하는 함수
def remove_task_time(task_id):
    task_times = load_task_times()
    if task_id in task_times:
        del task_times[task_id]
        save_task_times(task_times)
        
# 서버 시작 시 저장된 task_times 로드
task_times = load_task_times()

@app.route('/')
def index():   
    folders = fs.listdir_attr(path="/")  # 폴더 목록을 가져옵니다.
    folder_list = [{'id': str(folder['id']), 'name': folder['name']} for folder in folders if folder.get('is_directory')]
    return render_template('index.html', folders=folder_list, default_download_path_id=default_download_path_id)
    #return render_template('index.html', default_download_path_id=default_download_path_id)
    
@app.route('/add_task', methods=['POST'])
def add_single_task():
    data = request.json
    magnet_url = data.get('magnet_url')
    folder_id = data.get('wp_path_id', default_download_path_id)  # 기본 다운로드 경로 ID를 사용
    logging.info(f"Received magnet URL: {magnet_url} for Folder ID: {folder_id}")

    if not magnet_url:
        return jsonify({'error': 'No magnet URL provided'}), 400

    task_times = load_task_times()

    response = requests.post(
        "https://115.com/web/lixian/?ct=lixian&ac=add_task_url",
        headers={
            "Cookie": cookie,
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0"
        },
        data={
            "url": magnet_url,
            "wp_path_id": folder_id,
            "uid": uid,
            "app_ver": "25.0.2.1"
        }
    )

    result = response.json()
    logging.info(f"Task add result: {result}")

    if result.get('state'):
        task_id = result.get('info_hash', 'Unknown ID')
        original_size = format_size(result.get('size', 0))  # 작업 추가 시 가져온 크기를 기록

        # 이미 존재하는 task_id의 created_time을 유지하고 original_size를 추가
        if task_id not in task_times:
            task_times[task_id] = {
                'created_time': datetime.now().isoformat(),
                'folder_id': folder_id,
                'original_size': original_size
            }

        save_task_times(task_times)

        logging.info(f"Task added: ID={task_id}, Name={result.get('name', 'Unknown Name')}, Status={result.get('state')}, Folder ID={folder_id}, Created Time={task_times[task_id]['created_time']}, Original Size={original_size}")
        return jsonify({'status': 'success', 'result': task_id})
    else:
        logging.error(f"Error adding task: {result.get('error_msg', 'Unknown error')}")
        return jsonify({'error': f"Failed to add task: {result.get('error_msg', 'Unknown error')}"})

@app.route('/tasks/add', methods=['POST'])
def add_multiple_tasks():
    data = request.json
    urls = data.get('urls')
    folder_id = data.get('wp_path_id')  # wp_path_id를 받아옴

    if not urls:
        return jsonify({'error': 'No URLs provided'}), 400

    if not folder_id:
        return jsonify({'error': 'No folder ID provided'}), 400

    task_times = load_task_times()
    task_ids = []

    # URL 데이터를 URL[0], URL[1] 형식으로 변환
    url_data = {f"url[{i}]": url.strip() for i, url in enumerate(urls.split('\n')) if url.strip()}

    logging.info(f"Prepared URL data for request: {url_data}")

    try:
        response = requests.post(
            "https://115.com/web/lixian/?ct=lixian&ac=add_task_urls",  # 복수 URL 전송을 위한 엔드포인트 확인 필요
            headers={
                "Cookie": cookie,
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"
            },
            data={
                **url_data,
                "wp_path_id": folder_id,
                "uid": uid,
                "app_ver": "25.0.2.1"
            }
        )

        # 응답이 올바른 JSON 형식인지 확인
        try:
            result = response.json()
            logging.info(f"Result structure: {result}")

            if result.get('state'):
                for task_result in result.get('result', []):
                    task_id = task_result.get('info_hash', 'Unknown ID')
                    task_name = task_result.get('name', 'Unknown Name')
                    original_size = format_size(task_result.get('size', 0))  # 작업 추가 시 가져온 크기를 기록

                    # 이미 존재하는 task_id의 created_time을 유지하고 original_size를 추가
                    if task_id not in task_times:
                        task_times[task_id] = {
                            'created_time': datetime.now().isoformat(),  # 작업 추가 시점 기록
                            'folder_id': folder_id,
                            'original_size': original_size
                        }
                    else:
                        # 만약 task_id가 이미 있다면, original_size를 업데이트
                        task_times[task_id]['original_size'] = original_size

                    save_task_times(task_times)

                    task_ids.append(task_id)
                    logging.info(f"Task added: ID={task_id}, Name={task_name}, Status={task_result.get('state')}, Folder ID={folder_id}, Created Time={task_times[task_id]['created_time']}, Original Size={original_size}")
            else:
                logging.error(f"Error adding task: {result.get('error_msg', 'Unknown error')}")
        except requests.exceptions.JSONDecodeError:
            logging.error(f"Failed to decode JSON response: {response.text}")
            return jsonify({'error': 'Failed to decode server response as JSON'}), 500

    except Exception as e:
        logging.error(f"Exception occurred while sending request: {e}")
        return jsonify({'error': f"Exception occurred: {str(e)}"}), 500

    return jsonify({'status': 'success', 'result': task_ids})

@app.route('/folders', methods=['GET'])
def list_folders():
    try:
        folder_list = fs.listdir_attr(path="/")  # 루트 디렉토리의 폴더 목록 가져오기
        folders = []
        for folder in folder_list:
            if folder.get('is_directory'):
                folder_id = str(folder['id'])
                folder_name = folder['name']
                folder_id_to_name[folder_id] = folder_name  # folder_id_to_name에 추가
                logging.info(f"Folder ID: {folder_id}, Folder Name: {folder_name}")  # 디버깅 로그 추가
                folders.append({'id': folder_id, 'name': folder_name})
        return jsonify({'folders': folders})
    except Exception as e:
        logging.error(f"Error fetching folder list: {e}")
        return jsonify({'error': 'Failed to fetch folders'}), 500

    
@app.route('/tasks', methods=['GET'])
def list_tasks():
    tasks = []
    running_count = 0
    complete_count = 0

    all_tasks = offline_service.list()  # 모든 작업 가져오기
    task_times = load_task_times()  # JSON 파일에서 작업 시간 로드

    for task in all_tasks:
        task_id = task.get('info_hash', 'Unknown ID')

        # task_times에서 생성 시간, original_size, completed_time 가져오기
        if task_id in task_times:
            created_time = datetime.fromisoformat(task_times[task_id]['created_time'])
            completed_time = task_times[task_id].get('completed_time')
            original_size = task_times[task_id].get('original_size', None)
            
            if completed_time:
                completed_time = datetime.fromisoformat(completed_time)
        else:
            created_time = datetime.fromtimestamp(task.get('add_time', 0))
            completed_time = None
            original_size = None

        # original_size가 없을 경우 서버에서 가져옴
        if original_size is None or original_size == "0.0 B":
            original_size = format_size(task.get('size', 0))
            task_times[task_id] = {
                'created_time': created_time.isoformat(),
                'original_size': original_size,
                'folder_id': task.get('wp_path_id', 'N/A')
            }

            if completed_time:
                task_times[task_id]['completed_time'] = completed_time.isoformat()
            
            # task_times.json에 저장
            save_task_times(task_times)

        # 기본값으로 folder_id와 folder_name 초기화
        folder_id = task.get('wp_path_id', 'N/A')
        folder_name = folder_id_to_name.get(folder_id, 'N/A')

        folder_path = task.get('del_path', '').strip('/')
        target_name = folder_path.split('/')[-1]  # del_path의 마지막 부분을 추출

        full_folder_path = f"{folder_name}/{folder_path}" if folder_path else f"/{folder_name}"

        if task.get('percentDone', 0) == 100:
            # completed_time이 없는 경우에만 서버에서 etime 가져옴
            if 'completed_time' not in task_times[task_id]:
                try:
                    folder_attrs = fs.listdir_attr(f"/{folder_name}")
                    for attr in folder_attrs:
                        if attr['name'] == target_name:
                            completed_time = attr['etime']
                            task_times[task_id]['completed_time'] = completed_time.isoformat()
                            break
                    else:
                        completed_time = datetime.fromtimestamp(task.get('last_update', 0))
                        task_times[task_id]['completed_time'] = completed_time.isoformat()

                    complete_count += 1
                    save_task_times(task_times)
                except Exception as e:
                    logging.error(f"Error retrieving etime for folder {folder_id} at {full_folder_path}: {e}")
            else:
                complete_count += 1
        else:
            running_count += 1

        logging.info(f"Task ID: {task_id}, Folder ID: {folder_id}, Mapped Folder Name: {folder_name}, Completed Time: {completed_time}")

        task_info = {
            'task_id': task_id,
            'name': task.get('name', 'Unknown Name'),
            'status': 'Complete' if task.get('percentDone', 0) == 100 else 'Running',
            'created_time': created_time.strftime('%Y-%m-%d %H:%M:%S'),
            'completed_time': completed_time.strftime('%Y-%m-%d %H:%M:%S') if completed_time else '',
            'size': original_size,
            'percent': f"{task.get('percentDone', 0):.1f}",
            'folder_name': folder_name  # 폴더 이름 반환
        }
        tasks.append(task_info)

    return jsonify({'tasks': tasks, 'running_count': running_count, 'complete_count': complete_count})

@app.route('/tasks/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    try:
        offline_service.remove(task_id)
        remove_task_time(task_id)  # JSON 파일에서 해당 task_id 삭제
        return jsonify({'status': 'deleted'})
    except Exception as e:
        logging.error(f"Error deleting task {task_id}: {e}")
        return jsonify({'error': f"Failed to delete task {task_id}"}), 500

@app.route('/tasks/clear_completed', methods=['POST'])
def clear_completed_tasks():
    all_tasks = offline_service.list()  # 모든 작업 가져오기
    for task in all_tasks:
        if task['status'] == 2:  # 상태 2는 완료된 작업을 나타냅니다.
            offline_service.remove(task['info_hash'])
            task_id = task['info_hash']
            remove_task_time(task_id)  # JSON 파일에서 해당 task_id 삭제
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
