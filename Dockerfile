# 베이스 이미지로 Alpine Linux 사용
FROM python:3.11-alpine

# 작업 디렉토리 설정
WORKDIR /app

# 필요한 패키지 설치
RUN apk add --no-cache gcc musl-dev linux-headers tzdata

# 시간대 설정
ENV TZ=Asia/Seoul
RUN cp /usr/share/zoneinfo/Asia/Seoul /etc/localtime && echo "Asia/Seoul" > /etc/timezone

# Python 패키지 설치를 위한 requirements.txt 복사
COPY requirements.txt .

# Python 패키지 설치
RUN pip install --no-cache-dir -r requirements.txt

# Flask 애플리케이션 파일 복사
COPY app.py .
COPY templates ./templates

# Flask 앱 실행
CMD ["python", "app.py"]
