// 폴더 목록 토글
function toggleFolderList() {
    const folderListContainer = document.getElementById('folderListContainer');
    const selectedPathDisplayElement = document.getElementById('selectedPathDisplay');
    const currentPath = selectedPathDisplayElement.value;

    folderListContainer.style.display = folderListContainer.style.display === 'none' ? 'block' : 'none';

    if (folderListContainer.style.display === 'block') {
        fetchFolders(currentPath);  // 현재 선택된 경로에서 폴더 목록을 로드
    }
}

// 폴더 목록을 가져와서 표시
async function fetchFolders(targetFolderName) {
    try {
        const response = await fetch('/folders', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder_name: targetFolderName })
        });

        if (!response.ok) {
            throw new Error('Failed to load subfolders');
        }

        const data = await response.json();
        const folderListElement = document.getElementById('folderList');
        folderListElement.innerHTML = '';

        if (data.current_path !== '/') {
            const parentElement = document.createElement('div');
            parentElement.innerHTML = `<i class="bi bi-folder"></i> ..`;
            parentElement.classList.add('folder-item');
            parentElement.onclick = async () => {
                await fetchFolders('..');

                // 현재 경로에서 마지막 폴더를 제거한 후, 루트 처리
                let newPath = data.current_path.split('/').slice(0, -1).join('/');
                if (newPath === '') {
                    newPath = '/';
                }

                document.getElementById('selectedPathDisplay').value = newPath;
                document.getElementById('selectedPath').value = data.parent_folder_id;
            };
            folderListElement.appendChild(parentElement);
        } else {
            document.getElementById('selectedPathDisplay').value = '/';
            document.getElementById('selectedPath').value = '0';
        }

        data.folders.forEach(folder => {
            const folderElement = document.createElement('div');
            folderElement.innerHTML = `<i class="bi bi-folder"></i> ${folder.name}`;
            folderElement.classList.add('folder-item');

            folderElement.onclick = async () => {
                await fetchFolders(folder.name);
                selectFolder(folder.id, folder.name, data.current_path);
            };

            folderListElement.appendChild(folderElement);
        });

    } catch (error) {
        console.error('Error fetching folders:', error);
    }
}

// 폴더 선택 처리: 선택된 폴더 ID와 경로를 selectedPath와 selectedPathDisplay 요소에 업데이트.
function selectFolder(folderId, folderName, currentPath) {
    const selectedPathElement = document.getElementById('selectedPath');
    const selectedPathDisplayElement = document.getElementById('selectedPathDisplay');

    if (selectedPathElement) {
        selectedPathElement.value = folderId;
    } else {
        console.error('selectedPath element not found.');
        return;
    }

    if (selectedPathDisplayElement) {
        let fullPath;
        if (folderId === '0') {
            fullPath = '/';
        } else {
            // 현재 경로가 루트가 아니라면 현재 경로를 기준으로 새 경로 생성
            fullPath = currentPath === '/' ? `/${folderName}` : `${currentPath}/${folderName}`;
        }

        selectedPathDisplayElement.value = fullPath.replace('//', '/'); // 중복 슬래시 제거
    } else {
        console.error('selectedPathDisplay element not found.');
        return;
    }
}

// 페이지 로드 후 초기 설정
document.addEventListener('DOMContentLoaded', async function() {
    const selectedPathDisplayElement = document.getElementById('selectedPathDisplay');
    await fetchFolders(selectedPathDisplayElement.value); // 페이지 로드 시 기본 폴더의 내용을 로드
    await fetchTasks(); // 작업 목록을 가져옴

    setInterval(fetchTasks, 600000); // 주기적으로 작업 목록을 갱신

    // 작업추가 (addTaskForm.onsubmit)
    document.getElementById('addTaskForm').onsubmit = async function (e) {
        e.preventDefault();
        const loadingIcon = document.getElementById('loadingIcon');
        loadingIcon.style.display = 'inline-block'; // 로딩 아이콘 표시

        const selectedPathDisplay = document.getElementById('selectedPathDisplay').value;
    
        // 루트 폴더에 다운로드 시도하는 경우 경고 표시
        if (selectedPathDisplay.value === '/' || selectedPathDisplay.value === '' || selectedPath.value === '0') {
            alert("Cannot download to the root folder. Please select another folder.");
            loadingIcon.style.display = 'none';
            return;  // 여기서 반환하여 작업이 중단되도록 합니다.
        }

        const urls = document.getElementById('urls').value.split('\n'); // 엔터로 구분된 URL들
        const wp_path_id = document.getElementById('selectedPath').value;

        if (!urls || !wp_path_id) {
            alert("URL과 폴더 ID를 확인하세요.");
            loadingIcon.style.display = 'none';
            return;
        }
    
        for (const url of urls) {
            const response = await fetch('/tasks/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ urls: url, wp_path_id: wp_path_id }) // 폴더 ID와 함께 전송
            });
    
            const result = await response.json();
    
            if (result.errno === 911) {
                alert("공식 웹으로 1회 오프라인 다운로드를 시도하여 Captcha를 해지하세요.");
                loadingIcon.style.display = 'none';
                return;
            }
    
            if (!response.ok) {
                alert(`Failed to add task. Server responded with status: ${response.status}`);
                loadingIcon.style.display = 'none';
                return;
            }
        }
    
        document.getElementById('urls').value = '';
        await fetchTasks();
        loadingIcon.style.display = 'none'; // 로딩 아이콘 숨기기
    
        // 폴더 목록을 닫고 기본 폴더로 리셋
        document.getElementById('folderListContainer').style.display = 'none'; // 폴더 목록 닫기
    };
});

// 폴더 선택 확인: 
//  - /get_folder_id 경로로 GET 요청을 보내 현재 폴더의 ID를 가져옴.
//  - 가져온 폴더 ID를 selectedPath에, 폴더 경로를 selectedPathDisplay에 업데이트.
async function confirmSelection() {
    const loadingIcon = document.getElementById('loadingIcon');
    loadingIcon.style.display = 'inline-block'; // 로딩 아이콘 표시

    try {
        const response = await fetch('/get_folder_id', {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' }
        });

        const data = await response.json();
        if (data.folder_id) {
            // 루트 폴더가 선택되었는지 확인
            if (data.folder_id === "0") {
                alert("Root folder cannot be selected.");
                return; // 선택 취소
            }

            document.getElementById('selectedPath').value = data.folder_id;

            const fullPathResponse = await fetch('/get_full_path_name', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ folder_id: data.folder_id })
            });

            const fullPathData = await fullPathResponse.json();
            if (fullPathData.full_path_name) {
                document.getElementById('selectedPathDisplay').value = fullPathData.full_path_name;
            }
        } else {
            alert('Failed to get folder ID');
        }
    } catch (error) {
        console.error('Error getting folder ID:', error);
        alert('An error occurred while getting the folder ID');
    } finally {
        loadingIcon.style.display = 'none'; // 작업 완료 후 로딩 아이콘 숨기기
    }
}

// 작업 목록 불러오기
async function fetchTasks() {
    const refreshLoadingIcon = document.getElementById('refreshLoadingIcon');
    refreshLoadingIcon.style.display = 'inline-block'; // 로딩 아이콘 표시

    const response = await fetch('/tasks'); // /tasks 경로로 GET요청을 보내 현재 작업 목록을 가져와 화면에 표시
    const data = await response.json();

    console.log("Fetched task data:", data);  // 추가된 디버깅 로그

    const tasks = data.tasks;
    const runningCount = data.running_count;
    const completeCount = data.complete_count;
    
    const tasksList = document.getElementById('tasks');
    tasksList.innerHTML = '';
    
    document.getElementById('runningCount').textContent = runningCount;
    document.getElementById('completeCount').textContent = completeCount;

    tasks.forEach(task => {
        const tr = document.createElement('tr');
        const statusClass = task.status === 'Complete' ? 'complete' : 'running';
        
        tr.innerHTML = `
            <td class="${statusClass}" style="width: 30%;">${task.name}</td>
            <td class="${statusClass}">${task.status}</td>
            <td class="${statusClass}" style="font-size: smaller;">${task.created_time}${task.completed_time ? `<br>${task.completed_time}` : ''}</td>
            <td class="${statusClass}">${task.size}</td>
            <td>
                <div class="progress progress-bar-container">
                    <div class="progress-bar ${task.status === 'Complete' ? 'bg-secondary text-white' : 'bg-warning'}" role="progressbar" style="width: ${task.percent}%" aria-valuenow="${task.percent}" aria-valuemin="0" aria-valuemax="100">
                        <span>${task.percent}%</span>
                    </div>
                </div>
            </td>
            <td class="${statusClass}" style="white-space: pre-wrap; font-size: smaller;">${task.folder_name || 'N/A'}</td>
            <td>
                <button class="btn btn-secondary btn-sm" onclick="showRemoveOptions('${task.task_id}')">Remove</button>
            </td>
        `;
        
        tasksList.appendChild(tr);
    });
    refreshLoadingIcon.style.display = 'none'; // 작업 완료 후 로딩 아이콘 숨기기
}

async function clearCompletedTasks() {
    const clearLoadingIcon = document.getElementById('clearLoadingIcon');
    clearLoadingIcon.style.display = 'inline-block'; // 로딩 아이콘 표시

    await fetch('/tasks/clear_completed', { method: 'POST' });
    fetchTasks();

    clearLoadingIcon.style.display = 'none'; // 작업 완료 후 로딩 아이콘 숨기기
}

// Remove 버튼 클릭시 팝업 메뉴를 보여주는 함수
function showRemoveOptions(taskId) {
    const removePopup = document.getElementById('removePopup');
    removePopup.style.display = 'block';

    // 각 버튼에 대해 클릭 이벤트 설정
    removePopup.querySelectorAll('button').forEach(button => {
        const action = button.getAttribute('data-action');
        button.onclick = () => removeTask(taskId, action);
    });
}

// 실제로 Remove 작업을 수행하는 함수
function removeTask(taskId, action) {
    // const removeLoadingIcon = document.getElementById('removeLoadingIcon');
    // removeLoadingIcon.style.display = 'inline-block'; // 로딩 아이콘 표시

    const removePopup = document.getElementById('removePopup');
    removePopup.style.display = 'none'; // 팝업 닫기

    if (action === 'cancel') {
        return; // 아무 것도 하지 않음
    }

    const endpoint = action === 'delete_task_and_folder' ? `/tasks/${taskId}/delete_with_folder` : `/tasks/${taskId}`;

    fetch(endpoint, { method: 'DELETE' })
        .then(() => fetchTasks()) // 작업 목록을 다시 불러옴
        .catch(error => console.error('Error removing task:', error));
        //.finally(() => {
        //    removeLoadingIcon.style.display = 'none'; // 작업 완료 후 로딩 아이콘 숨기기
        //});
}
