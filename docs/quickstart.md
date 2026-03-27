# Quick Start Guide

## 사전 요구사항

- Docker + Docker Compose v2
- OpenAI API 키 (필수)
- Slack Bot 토큰 (선택)

## 1. 빠른 시작 (5분)

```bash
# 클론
git clone https://github.com/donggyu-ralph/error_log_agent_v2.git
cd error_log_agent_v2

# 환경변수 설정
cp .env.example .env
# .env 파일에서 OPENAI_API_KEY 입력

# 실행
docker compose up -d

# 확인
open http://localhost:3000
```

## 2. 서비스 구성

| 서비스 | 포트 | 설명 |
|--------|------|------|
| Frontend | 3000 | 웹 대시보드 (React) |
| Agent API | 8000 | 에이전트 API + Slack Bot |
| Pipeline | 8001 | 데이터 파이프라인 (모니터링 대상) |
| PostgreSQL | 5432 | DB |
| MinIO | 9000/9001 | 오브젝트 스토리지 |

## 3. 사용 방법

### 에러 발생시키기

```bash
# CSV 파일 업로드 → Qwen API 에러 발생
echo "name,value
test,100" > /tmp/test.csv

curl -X POST http://localhost:8001/api/v1/pipelines -F "file=@/tmp/test.csv"
```

### 흐름

1. 파이프라인에 파일 업로드 → 에러 발생
2. 에이전트가 2분마다 로그 수집 → 에러 감지
3. Slack에 보고서 전송 (Slack 설정 시)
4. 웹 대시보드에서 확인: http://localhost:3000

### 모니터링 서비스 추가

웹 대시보드 → Services 탭 → + Add Service

### Slack 연동

1. https://api.slack.com/apps 에서 앱 생성
2. Socket Mode 활성화
3. 토큰을 .env에 입력
4. `docker compose restart agent`

## 4. 로그 확인

```bash
docker compose logs agent -f      # 에이전트 로그
docker compose logs target-service -f  # 파이프라인 로그
docker compose logs -f             # 전체 로그
```

## 5. 중지

```bash
docker compose down        # 중지
docker compose down -v     # 중지 + 데이터 삭제
```

## 아키텍처

```
[사용자] → [Frontend :3000] → [Agent API :8000] → [PostgreSQL]
                                    ↓
                            [Slack Bot] ← 2분마다 로그 수집
                                    ↓
                         [Pipeline :8001] → [Qwen API] → [MinIO]
```
