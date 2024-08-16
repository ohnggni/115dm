# 115DM

이 프로젝트는 Docker Compose를 사용하여 Flask 애플리케이션을 실행하는 방법을 설명합니다.

## Docker Compose로 애플리케이션 실행하기

1. 이 레포지토리를 클론합니다.

   ```sh
   git clone https://github.com/ohnggni/115dm.git
   cd 115dm

2. docker-compose.yml 파일을 수정합니다. (쿠키값, 본인계정, 기본 다운로드 경로ID를 본인 것에 맞게 넣고, 필요 시 포트도 수정합니다)
3. Docker Compose를 사용하여 컨테이너를 빌드하고 실행합니다.
   ```sh
   docker-compose up --build

4. Docker Compose를 사용하여 컨테이너를 실행합니다.
   ```sh
   docker-compose up -d

5. 애플리케이션이 실행되면 웹 브라우저에서 http://[ip_address]:5556로 접속하여 확인할 수 있습니다.
   
<img width="1329" alt="스크린샷 2024-08-16 15 34 54" src="https://github.com/user-attachments/assets/35a8fc5f-5fef-44f3-822b-1e5f1f9730d0">



## [V2] 주요 변경사항**
1) 파이썬 모듈 교체: 기존 py115 -> p115
2) 파일 다운로드 경로 지정: 현재는 루트 폴더 내 서브디렉토리 단계까지만 선택 가능
3) 2번 구현을 위해 add task 부분 전면 수정
4) 시작/완료 시간 기록을 위해 별도로 task_times.json파일을 생성
5) 다수의 마그넷 파일 다운로드 방식 변경
6) 기타 화면 레이아웃 소폭 변경.

## [기타] 팁**
1) 완료 작업 목록을 주기적으로 삭제하는 명령(CURL활용):
   ```sh
   crontab -e
   */5 * * * * curl -X POST http://[ip:port]/tasks/clear_completed
