import os
import logging
import json
import time
from datetime import datetime
from flask import Flask, request, jsonify, render_template, session
from p115client import P115Client, tool
from threading import Lock

# --- 1. 초기 설정 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s')
app = Flask(__name__)
app.secret_key = os.urandom(24)

COOKIE = os.getenv('P115_COOKIE')
DEFAULT_DOWNLOAD_PATH_ID = os.getenv('C_FolderId', '0')
UID = os.getenv('UID')

client = None
try:
    if not all([COOKIE, UID]):
        raise EnvironmentError("환경변수 P115_COOKIE, UID가 설정되어야 합니다.")
    client = P115Client(COOKIE)
    logging.info("P115Client 객체 초기화 성공.")
except Exception as e:
    logging.error(f"CRITICAL: P115Client 객체 초기화 실패: {e}", exc_info=True)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
FOLDER_MAPPING_FILE = os.path.join(DATA_DIR, 'folder_mapping.json')
os.makedirs(DATA_DIR, exist_ok=True)
data_lock = Lock()

# --- 2. Helper 함수 ---
def load_from_json(file_path, default_data={}):
    with data_lock:
        if not os.path.exists(file_path): return default_data
        try:
            with open(file_path, 'r', encoding='utf-8') as f: return json.load(f)
        except: return default_data

def save_to_json(file_path, data):
    with data_lock:
        try:
            with open(file_path, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4)
        except Exception as e: logging.error(f"JSON 저장 실패: {e}")

FOLDER_MAPPING = load_from_json(FOLDER_MAPPING_FILE)

def update_and_save_folder_mapping(items):
    global FOLDER_MAPPING
    updated = False
    for item in items:
        folder_id_str = str(item.get("id") or item.get("cid"))
        folder_name = item.get("name") or item.get("n")
        if folder_id_str and folder_name and FOLDER_MAPPING.get(folder_id_str) != folder_name:
            FOLDER_MAPPING[folder_id_str] = folder_name
            updated = True
    if updated:
        save_to_json(FOLDER_MAPPING_FILE, FOLDER_MAPPING)

def get_status_string(status_code):
    status_map = {0: "대기중", 1: "진행중", 2: "완료", -1: "실패"}
    return status_map.get(status_code, "알 수 없음")

def format_size(size_bytes):
    if not isinstance(size_bytes, (int, float)) or size_bytes == 0: return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB"); i = int(abs(size_bytes).bit_length() / 10)
    p = 1024 ** i; s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

# --- 3. Flask 라우팅 ---
@app.route('/')
def index_page():
    if not client: return "115 클라이언트가 초기화되지 않았습니다.", 500
    session['current_folder_id'] = DEFAULT_DOWNLOAD_PATH_ID
    default_folder_name = FOLDER_MAPPING.get(str(DEFAULT_DOWNLOAD_PATH_ID), "/")
    if default_folder_name == "/":
        try:
            attr = tool.get_attr(client, id=DEFAULT_DOWNLOAD_PATH_ID)
            ancestors = list(tool.get_ancestors(client, attr=attr))
            if ancestors:
                update_and_save_folder_mapping(ancestors)
                default_folder_name = "/" + "/".join(reversed([p["name"] for p in ancestors]))
        except Exception as e:
            logging.error(f"기본 폴더 정보 조회 실패: {e}")
            default_folder_name = "경로 조회 실패"
    return render_template('index.html', default_download_path_id=DEFAULT_DOWNLOAD_PATH_ID, default_download_path_name=default_folder_name)

@app.route('/folders', methods=['POST'])
def get_folders_handler():
    if not client: return jsonify({"error": "클라이언트가 초기화되지 않았습니다."}), 500
    target_folder_name = request.json.get('folder_name')
    current_cid = session.get('current_folder_id', '0')
    try:
        next_cid = current_cid
        if target_folder_name == '..':
            if current_cid != '0':
                attr = tool.get_attr(client, id=current_cid)
                next_cid = str(attr.get("parent_id", "0"))
        elif target_folder_name and not os.path.ismount(target_folder_name):
            items = list(tool.iterdir(client, cid=current_cid))
            update_and_save_folder_mapping(items)
            for item in items:
                if item.get("is_directory") and item.get("name") == target_folder_name:
                    next_cid = str(item.get("id"))
                    break
        session['current_folder_id'] = next_cid
        items = list(tool.iterdir(client, cid=next_cid))
        update_and_save_folder_mapping(items)
        subfolders = [{"id": str(item.get("id")), "name": item.get("name")} for item in items if item.get("is_directory")]
        current_path, parent_id = "/", "0"
        if next_cid != '0':
            current_path = FOLDER_MAPPING.get(str(next_cid), "...")
            attr = tool.get_attr(client, id=next_cid)
            parent_id = str(attr.get("parent_id", "0"))
        return jsonify({
            'folders': subfolders, 'current_path': current_path,
            'parent_folder_id': parent_id
        })
    except Exception as e:
        return jsonify({"error": "폴더를 처리하는 중 오류가 발생했습니다."}), 500

@app.route('/tasks', methods=['GET'])
def get_tasks():
    if not client: return jsonify({"error": "클라이언트가 초기화되지 않았습니다."}), 500
    try:
        api_tasks = list(tool.offline_iter(client))
        processed_tasks, running_count, complete_count = [], 0, 0
        
        for task in api_tasks:
            status_str = get_status_string(task.get('status'))
            if status_str == "완료": complete_count += 1
            elif status_str == "진행중": running_count += 1
            
            created_time = ""
            if add_time := task.get('add_time'):
                created_time = datetime.fromtimestamp(add_time).strftime('%y/%m/%d %H:%M')
            
            processed_tasks.append({
                'task_id': task.get('info_hash'),
                'name': task.get('name'),
                'status': status_str,
                'percent': f"{task.get('percentDone', 0):.1f}",
                'size': format_size(task.get('size', 0)),
                'created_time': created_time,
                'completed_time': "", # 요청대로 종료 시간 제거
                'folder_name': FOLDER_MAPPING.get(str(task.get('wp_path_id')), 'N/A')
            })
        return jsonify({'tasks': processed_tasks, 'running_count': running_count, 'complete_count': complete_count})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/tasks/add', methods=['POST'])
def add_tasks():
    if not client: return jsonify({"error": "클라이언트가 초기화되지 않았습니다."}), 500
    data = request.json
    urls_string = data.get('urls')
    folder_id = data.get('wp_path_id')
    
    if not urls_string or not folder_id or folder_id == '0':
        return jsonify({"error": "유효한 URL과 저장할 폴더를 지정해야 합니다."}), 400
        
    try:
        urls_to_add = [u.strip() for u in urls_string.replace(',', '\n').split('\n') if u.strip()]
        
        url_payload = {f"url[{i}]": u for i, u in enumerate(urls_to_add)}
        payload = {"wp_path_id": folder_id, "uid": UID, **url_payload}
        
        response = client.request("https://115.com/web/lixian/?ct=lixian&ac=add_task_urls", "POST", data=payload)
        
        return jsonify(response)
    except Exception as e: 
        return jsonify({"error": str(e)}), 500

@app.route('/tasks/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    if not client: return jsonify({"error": "클라이언트가 초기화되지 않았습니다."}), 500
    try:
        url = "https://115.com/web/lixian/?ct=lixian&ac=task_del"
        payload = {f"hash[0]": task_id, "uid": UID}
        client.request(url, "POST", data=payload)
        return jsonify({'status': 'deleted'})
    except Exception as e:
        return jsonify({'error': f"Failed to delete task {task_id}"}), 500

@app.route('/tasks/clear_completed', methods=['POST'])
def clear_completed_tasks():
    if not client: return jsonify({"error": "클라이언트가 초기화되지 않았습니다."}), 500
    try:
        url = "https://115.com/web/lixian/?ct=lixian&ac=task_clear"
        client.request(url, "POST", data={"flag": 0})
        return jsonify({"status": "success"})
    except Exception as e: return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    if client: app.run(host='0.0.0.0', port=5000)
    else: print("앱을 실행할 수 없습니다. 환경변수를 확인하세요.")
    
@app.route('/tasks/<task_id>/delete_with_folder', methods=['DELETE'])
def delete_task_and_folder(task_id):
    return delete_task(task_id)
