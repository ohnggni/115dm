import os
import logging
import time
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from p115 import P115Client, P115Offline, P115FileSystem
import requests
import json
from urllib.parse import urlencode

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

# Task 저장 블럭-------------------------------------------------------------------
TASK_TIMES_FILE = '/app/data/task_times.json' # 저장할 JSON 파일 경로 설정

def load_task_times(): # 파일에서 task_times를 로드하는 함수
    if os.path.exists(TASK_TIMES_FILE):
        with open(TASK_TIMES_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_task_times(task_times): # task_times를 JSON 파일에 저장하는 함수
    existing_task_times = load_task_times() # 기존 파일의 내용을 로드합니다.
    
    for task_id, times in task_times.items(): # 새로운 task_times를 기존 task_times에 병합합니다.
        if task_id not in existing_task_times: # 이미 존재하는 task_id에 대해서는 업데이트하지 않음
            existing_task_times[task_id] = times
    
    with open(TASK_TIMES_FILE, 'w') as f: # 병합된 내용을 다시 저장합니다.
        json.dump(existing_task_times, f, indent=4, default=str)

def remove_task_time(task_id): # 특정 task_id를 JSON 파일에서 삭제하는 함수
    task_times = load_task_times()
    if task_id in task_times:
        del task_times[task_id]
        save_task_times(task_times)
        
# 폴더 매핑 블럭 -------------------------------------------------------------------    
def build_folder_mapping(starting_path="/"):
    """주어진 경로에 대한 폴더 매핑을 수행합니다. """
    fs.chdir(starting_path)
    folders = fs.dictdir()  # 폴더 ID와 이름의 딕셔너리 생성

    for folder_id, folder_name in folders.items():
        folder_id_to_name[str(folder_id)] = folder_name
        logging.info(f"Folder ID: {folder_id}, Full Path: {folder_name}")

    save_mapping_to_file()  # 매핑 데이터를 저장

def explore_folder(folder_id):
    """ 사용자가 탐색한 폴더의 서브디렉토리를 매핑합니다. """
    if folder_id not in folder_id_to_name:
        logging.warning(f"Folder ID {folder_id} not found in current mapping.")
        return

    current_path = folder_id_to_name[folder_id]
    build_folder_mapping(current_path)
    save_mapping_to_file() # 폴더 매핑 정보를 저장합니다.

def get_full_folder_path(folder_id):
    """ 주어진 폴더 ID에 대한 전체 경로를 반환합니다. """
    return folder_id_to_name.get(folder_id, 'N/A')

def save_mapping_to_file():
    with open('/app/data/folder_mapping.json', 'w') as f:
        json.dump(folder_id_to_name, f, indent=4)

def load_mapping_from_file():
    global folder_id_to_name
    if os.path.exists('/app/data/folder_mapping.json'):
        with open('/app/data/folder_mapping.json', 'r') as f:
            folder_id_to_name = json.load(f)
        logging.info("Folder mapping loaded from file.")

def format_size(size):
    """ 파일 크기를 적절한 단위로 변환하는 헬퍼 함수. """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
        
# 서버 시작시 로드 블럭 -----------------------------------------------------------
task_times = load_task_times() # 서버 시작 시 저장된 task_times 로드
build_folder_mapping() # 서버 시작 시 매핑 데이터 구축
load_mapping_from_file() # 서버 시작 시 매핑 데이터 로드

# app.route 블럭 index ------------------------------------------------------------------
@app.route('/')
def index():
    fs.chdir('/')
    build_folder_mapping('/')  # 루트 디렉토리의 매핑 데이터를 구축  
    current_folder_name = folder_id_to_name.get(default_download_path_id, "N/A") # default_download_path_id에 해당하는 폴더 경로를 찾음
    # current_folder_name이 '/'로 시작하는지 확인하고, 그렇지 않으면 '/'를 추가
    full_path_name = f"{current_folder_name}" if current_folder_name.startswith('/') else f"/{current_folder_name}"

    folders = fs.listdir_attr(path='/')
    folder_list = [{'id': str(folder['id']), 'name': folder['name']} for folder in folders if folder.get('is_directory')]
    
    return render_template('index.html', folders=folder_list, default_download_path_id=default_download_path_id, default_download_path_name=full_path_name)

# app.route 블럭 folder 탐색 관련 -------------------------------------------------------
@app.route('/folders', methods=['GET']) # 루트 디렉터리의 폴더 목록을 가져오는 기능을 수행
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

@app.route('/folders', methods=['POST'])
def change_directory():
    data = request.json
    target_folder_name = data.get('folder_name')

    try:
        if target_folder_name == '..':
            # 현재 디렉토리 정보를 가져옴
            current_path = fs.getcwd()
            logging.info(f"Current path: {current_path}")

            # 현재 경로에서 마지막 폴더 이름을 제거하여 상위 폴더 경로를 만듦
            parent_path = '/'.join(current_path.rstrip('/').split('/')[:-1])
            if not parent_path:
                parent_path = '/'  # 루트 폴더로 이동

            logging.info(f"Resolved parent path: {parent_path}")
            fs.chdir(parent_path)
            logging.info(f"Changed directory to parent path: {parent_path}")

        else:
            # 특정 폴더로 이동
            fs.chdir(target_folder_name)
            logging.info(f"Changed directory to: {target_folder_name}")

        # 현재 경로 및 하위 폴더 목록을 반환
        current_path = fs.getcwd()
        folders = fs.listdir_attr(path=current_path)
        # logging.info(f"Folders in new path: {folders}")

        # 새로 이동한 폴더의 parent ID 확인
        current_folder_id = fs.getcid()
        new_folder_attrs = fs.listdir_attr(current_path)
        parent_folder_id = '0'
        for attr in new_folder_attrs:
            # logging.info(f"Checking new folder attribute: {attr}")
            # 각 속성의 ancestors를 탐색하여 현재 폴더의 id와 일치하는 항목을 찾음
            for ancestor in attr.get('ancestors', []):
                # logging.info(f"Checking new ancestor: {ancestor}")
                if str(ancestor['id']) == str(current_folder_id):
                    parent_folder_id = str(ancestor['parent_id'])
                    logging.info(f"Found matching ancestor in new path. Parent ID: {parent_folder_id}")
                    break

            # parent_id를 찾았다면 더 이상 탐색하지 않음
            if parent_folder_id != '0':
                break
        
        logging.info(f"Final Parent folder ID after change: {parent_folder_id}")
        
        # 폴더 매핑 정보를 업데이트하고 저장합니다.
        folder_id_to_name[str(current_folder_id)] = current_path
        save_mapping_to_file()

        folder_list = [{'id': str(folder['id']), 'name': folder['name']} for folder in folders if folder.get('is_directory')]

        return jsonify({'folders': folder_list, 'current_path': current_path, 'parent_folder_id': parent_folder_id})

    except Exception as e:
        logging.error(f"Error fetching folders: {e}")
        return jsonify({'error': 'Failed to fetch folders', 'message': str(e)}), 500

@app.route('/get_folder_id', methods=['GET'])
def get_folder_id():
    try:
        current_folder_id = str(fs.getcid()) # 현재 위치의 폴더 ID를 가져옴
        return jsonify({'folder_id': current_folder_id})
    except Exception as e:
        return jsonify({'error': 'Failed to get folder ID', 'message': str(e)}), 500 
    
@app.route('/get_full_path_name', methods=['POST'])
def get_full_path_name():
    try:
        data = request.json
        folder_id = data.get('folder_id')

        # 루트 폴더인 경우 경로를 '/'로 설정
        if folder_id == '0':
            full_path_name = '/'
        else:
            current_path = fs.getcwd()
            folder_name = folder_id_to_name.get(folder_id, '')
            full_path_name = f"{current_path}/{folder_name}".replace('//', '/')

            if full_path_name.endswith('/'):
                full_path_name = full_path_name.rstrip('/')

        return jsonify({'full_path_name': full_path_name})

    except Exception as e:
        return jsonify({'error': 'Failed to get full path name', 'message': str(e)}), 500

# app.route 블럭 task 추가 관련 -------------------------------------------------------
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
        }
    )

    result = response.json()
    logging.info(f"Task add result: {result}")

    if result.get('state'):
        task_id = result.get('info_hash', 'Unknown ID')
        original_size = format_size(result.get('size', 0))  # 작업 추가 시 가져온 크기를 기록
        
        if task_id not in task_times: # 이미 존재하는 task_id의 created_time을 유지하고 original_size를 추가
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
    
    # URL 데이터를 URL[0], URL[1] 형식으로 변환 (','로 구분)
    url_data = {f"url[{i}]": url.strip() for i, url in enumerate(urls.split(',')) if url.strip()}
    
    logging.info(f"Generated url_data: {url_data}") # url_data의 내용을 로그로 출력

    # POST 데이터 설정
    post_data = {
        "wp_path_id": folder_id,
        "savepath": "",
        "uid": uid,
        **url_data  # URL 배열 데이터 추가
    }
    
    logging.info(f"Prepared URL data for request: {post_data}") # post_data의 내용을 로그로 출력

    try:
        response = requests.post(
            "https://115.com/web/lixian/?ct=lixian&ac=add_task_urls",
            headers={
                "Cookie": cookie,
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
            },
            data=post_data  # 데이터를 한 번에 전송
        )
        
        try: # 응답이 올바른 JSON 형식인지 확인
            result = response.json()
            logging.info(f"Result structure: {result}")

            if result.get('state'):
                for task_result in result.get('result', []):
                    task_id = task_result.get('info_hash', 'Unknown ID')
                    task_name = task_result.get('name', 'Unknown Name')
                    original_size = format_size(task_result.get('size', 0))  # 작업 추가 시 가져온 크기를 기록

                    if task_id not in task_times:
                        task_times[task_id] = {
                            'created_time': datetime.now().isoformat(),  # 작업 추가 시점 기록
                            'folder_id': folder_id,
                            'original_size': original_size
                        }
                    else:
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

# app.route 블럭: 작업목록을 보여주는 기능 수행 -------------------------------------------------------
@app.route('/tasks', methods=['GET'])
def list_tasks():
    tasks = []
    running_count = 0
    complete_count = 0

    all_tasks = offline_service.list()
    task_times = load_task_times()

    for task in all_tasks:
        task_id = task.get('info_hash', 'Unknown ID')

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

        if original_size is None or original_size == "0.0 B":
            original_size = format_size(task.get('size', 0))
            task_times[task_id] = {
                'created_time': created_time.isoformat(),
                'original_size': original_size,
                'folder_id': task.get('wp_path_id', 'N/A')
            }

            if completed_time:
                task_times[task_id]['completed_time'] = completed_time.isoformat()
            save_task_times(task_times)

        folder_id = task_times[task_id].get('folder_id', 'N/A')
        
        if folder_id not in folder_id_to_name:  # 기존 매핑에 없을 경우 매핑을 시도합니다.
            try:
                explore_folder(folder_id)  # 탐색 시 해당 폴더의 매핑 수행
            except Exception as e:
                logging.error(f"Error exploring folder for ID {folder_id}: {e}")
                folder_name = 'N/A'
        folder_name = folder_id_to_name.get(folder_id, 'N/A')

        folder_path = task.get('del_path', '').strip('/')
        target_name = folder_path.split('/')[-1]

        full_folder_path = f"{folder_name}/{folder_path}".replace('//', '/') if folder_path else f"/{folder_name}"

        if task.get('percentDone', 0) == 100:
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
            'folder_name': folder_name
        }
        tasks.append(task_info)

    return jsonify({'tasks': tasks, 'running_count': running_count, 'complete_count': complete_count})

@app.route('/tasks/<task_id>', methods=['DELETE']) # 작업목록을 json파일에서 삭제하는 기능 수행
def delete_task(task_id):
    try:
        offline_service.remove(task_id)
        remove_task_time(task_id)  # JSON 파일에서 해당 task_id 삭제
        return jsonify({'status': 'deleted'})
    except Exception as e:
        logging.error(f"Error deleting task {task_id}: {e}")
        return jsonify({'error': f"Failed to delete task {task_id}"}), 500

@app.route('/tasks/clear_completed', methods=['POST']) # 완료된 작업을 json파일에서 일괄 삭제하는 기능 수행
def clear_completed_tasks():
    all_tasks = offline_service.list()  # 모든 작업 가져오기
    for task in all_tasks:
        if task['status'] == 2:  # 상태 2는 완료된 작업을 나타냅니다.
            offline_service.remove(task['info_hash'])
            task_id = task['info_hash']
            remove_task_time(task_id)  # JSON 파일에서 해당 task_id 삭제
    return jsonify({'status': 'completed tasks cleared'})

@app.route('/tasks/<task_id>/delete_with_folder', methods=['DELETE']) # 완료된 작업목록과 폴더를 함께 삭제하는 기능 수행
def delete_task_and_folder(task_id):
    try:
        logging.info(f"Attempting to delete task and associated folder for task ID: {task_id}")
        # task_times를 로드하고, 해당 task_id에 연관된 파일 ID와 경로 ID를 가져옵니다.
        task_times = load_task_times()
        all_tasks = offline_service.list()

        file_id = None
        wp_path_id = None
        for task in all_tasks:
            if task.get('info_hash') == task_id:
                file_id = task.get('file_id')  # 작업에 연결된 파일 ID를 가져옵니다.
                wp_path_id = task.get('wp_path_id')  # 작업에 연결된 경로 ID를 가져옵니다.
                break

        # 파일 삭제 (file_id와 wp_path_id가 모두 존재할 경우)
        if file_id and wp_path_id:
            try:
                delete_url = "https://webapi.115.com/rb/delete"
                headers = {
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Cookie": cookie,
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0",
                }
                payload = {
                    "pid": wp_path_id,
                    "fid[0]": file_id,
                    "ignore_warn": "1"
                }
                response = requests.post(delete_url, headers=headers, data=payload)

                if response.status_code == 200 and response.json().get("state", False):
                    logging.info(f"Successfully deleted folder with ID: {file_id} under folder ID: {wp_path_id}")
                else:
                    logging.error(f"Failed to delete folder. Response: {response.text}")
                    return jsonify({'error': 'Failed to delete folder'}), 500

            except Exception as e:
                logging.error(f"Error occurred while trying to delete folder with ID: {file_id}, Error: {str(e)}")
                return jsonify({'error': f"Exception occurred: {str(e)}"}), 500
        else:
            logging.info(f"No folder associated with task ID: {task_id}, skipping folder deletion.")
            return jsonify({'error': 'No associated folder found'}), 400

        # 파일 삭제가 성공한 경우에만 작업 목록을 삭제합니다.
        offline_service.remove(task_id)
        remove_task_time(task_id)  # JSON 파일에서 해당 task_id 삭제
        logging.info(f"Task {task_id} removed from the offline service.")

        return jsonify({'status': 'success'}), 200

    except Exception as e:
        logging.error(f"Exception occurred while deleting task {task_id} and folder: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
