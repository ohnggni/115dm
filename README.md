# 115offdn_manager

이 프로젝트는 Docker Compose를 사용하여 Flask 애플리케이션을 실행하는 방법을 설명합니다.

## Docker Compose로 애플리케이션 실행하기

1. 이 레포지토리를 클론합니다.

   ```sh
   git clone https://github.com/ohnggni/115dm.git
   cd 115dm

2. docker-compose.yml 파일을 수정합니다. (쿠키값을 본인 것에 맞게 넣고, 필요 시 포트도 수정합니다)
3. Docker Compose를 사용하여 컨테이너를 빌드하고 실행합니다.
   ```sh
   docker-compose up --build

4. Docker Compose를 사용하여 컨테이너를 실행합니다.
   ```sh
   docker-compose up

5. 애플리케이션이 실행되면 웹 브라우저에서 http://[ip_address]:5555로 접속하여 확인할 수 있습니다.
   
   <img width="987" alt="스크린샷 2024-07-31 16 17 30" src="https://github.com/user-attachments/assets/77177b4e-d2b0-4415-8281-981ccc4ba23f">
