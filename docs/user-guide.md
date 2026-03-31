# Error Log Agent v2 — 사용 가이드

## 1. 설치 및 실행

### Docker Compose (권장)

```bash
# 클론
git clone https://github.com/donggyu-ralph/error_log_agent_v2.git
cd error_log_agent_v2

# 환경변수 설정
cp .env.example .env
# .env 파일을 열어 아래 값 입력:
#   OPENAI_API_KEY=sk-proj-...    (필수)
#   SLACK_APP_TOKEN=xapp-...      (Slack 알림 시 필수)
#   SLACK_BOT_TOKEN=xoxb-...      (Slack 알림 시 필수)

# 실행
docker compose up -d

# 접속
open http://localhost:3000
```

### 서비스 구성

| 서비스 | 포트 | 설명 |
|--------|------|------|
| 대시보드 | http://localhost:3000 | 웹 UI |
| 에이전트 API | http://localhost:8000 | 백엔드 |
| 파이프라인 | http://localhost:8001 | 모니터링 대상 (테스트용) |
| MinIO Console | http://localhost:9001 | 오브젝트 스토리지 |

---

## 2. 첫 시작

### 2.1 로그인

- 브라우저에서 `http://localhost:3000` 접속
- 초기 Admin 계정: `admin@atdev.co.kr` / `admin123`
- 또는 회원가입 후 사용

### 2.2 역할

| 역할 | 대시보드 열람 | 서비스 관리 | 승인/거절 | 사용자 관리 |
|------|:---:|:---:|:---:|:---:|
| Viewer | O | X | X | X |
| Operator | O | O | O | X |
| Admin | O | O | O | O |

Admin이 다른 사용자의 역할을 변경할 수 있습니다.

---

## 3. 서비스 등록

### 3.1 서비스 추가

1. 좌측 메뉴 **Services** 클릭
2. **+ Add Service** 버튼
3. 정보 입력:
   - **Name**: 서비스 이름 (예: `data-pipeline`)
   - **Source Type**: `K8s Pod` 또는 `Remote File`
   - K8s Pod인 경우: **Namespace** + **Label Selector** (예: `pipeline`, `app=data-pipeline`)
   - Remote File인 경우: **Log Path** (예: `host:path` 형식)
4. **Save**

등록하면:
- 본인이 **Owner**가 됨
- Slack 채널 `#svc-{서비스명}`이 자동 생성됨 (Slack 연동 시)
- 에이전트가 2분마다 해당 서비스의 로그를 수집 시작

### 3.2 멤버 초대

1. **Services** → 서비스 이름 클릭 → 상세 페이지
2. 이메일 입력 후 **초대** 버튼
3. 초대된 멤버는:
   - 해당 서비스의 에러를 대시보드에서 볼 수 있음
   - Slack 채널에 자동 추가됨
   - 에러에 대해 승인/거절 가능 (Operator 이상)

### 3.3 권한

- **Owner**: 서비스 설정 변경, 멤버 초대/제거, 서비스 삭제
- **Member**: 에러 조회, 승인/거절
- **비멤버**: 해당 서비스 에러를 볼 수 없음
- **Admin**: 모든 서비스 접근 가능

---

## 4. 에러 모니터링

### 4.1 대시보드

- **Dashboard** 페이지: 에러 발생 추이 차트, 타입별 통계
- 내가 속한 서비스의 에러만 표시됨 (Admin은 전체)
- stat 카드 클릭 시 해당 페이지로 이동

### 4.2 Error Logs

- 에러 목록 (20개씩 페이징)
- 서비스별 필터 가능
- 행 클릭 → 상세 보기 (traceback, 파일 위치)

### 4.3 Fix History

- 코드 수정 이력
- 행 클릭 → 상세 패널 (수정 계획, diff, Git 브랜치, 배포 상태)

---

## 5. Slack 연동

### 5.1 Slack App 생성

1. https://api.slack.com/apps → **Create New App**
2. **Socket Mode** 활성화
3. **Event Subscriptions** → `app_mention` 추가
4. **Interactivity & Shortcuts** → 활성화
5. **OAuth & Permissions** → Bot Token Scopes:
   - `chat:write`, `channels:manage`, `channels:join`, `groups:write`, `users:read`
6. 토큰을 `.env`에 입력

### 5.2 알림 흐름

```
에러 발생 → 에이전트 감지 (2분 이내) → Slack 서비스 채널에 보고서

보고서 내용:
  - 서비스명, 에러 타입, 발생 위치, traceback
  - 분석 결과 + 수정 계획
  - [승인] [거절] [피드백] 버튼

승인 → 코드 수정 → 이미지 빌드 → 스테이징 검증 → 프로덕션 배포
       (각 단계가 Slack에 실시간 보고됨)

배포 완료 → [PR 생성] [바로 Merge] [브랜치만 유지] 버튼
```

### 5.3 피드백

에이전트의 수정 방향이 마음에 들지 않으면:
1. **[피드백]** 버튼 클릭
2. 모달에 의견 입력 (예: "timeout을 300초로 늘려줘")
3. 에이전트가 피드백을 반영하여 **재분석** → 새 보고서 전송
4. 새 보고서에서 **[승인]**

---

## 6. 에러 발생시키기 (테스트)

### curl로 파일 업로드

```bash
# 정상 파일 (Qwen API로 분석 → 성공 또는 타임아웃)
echo "name,value
test,100" > /tmp/test.csv
curl -X POST http://localhost:8001/api/v1/pipelines -F "file=@/tmp/test.csv"

# 지원하지 않는 확장자 (즉시 에러)
echo "data" > /tmp/test.xyz
curl -X POST http://localhost:8001/api/v1/pipelines -F "file=@/tmp/test.xyz"
```

### K8s 환경에서

```bash
kubectl run upload --rm -it --restart=Never --image=curlimages/curl -n pipeline --command -- \
  sh -c "echo 'a,b' > /tmp/t.xyz && curl -s -X POST http://data-pipeline.pipeline.svc:8000/api/v1/pipelines -F file=@/tmp/t.xyz"
```

파일 업로드 후 2분 내에 Slack 알림이 옵니다.

---

## 7. 로그 확인

### Docker Compose

```bash
docker compose logs agent -f           # 에이전트
docker compose logs target-service -f  # 파이프라인
docker compose logs -f                 # 전체
```

### K8s

```bash
kubectl logs -n pipeline -l app=error-log-agent -f
kubectl logs -n pipeline -l app=data-pipeline -f
```

---

## 8. 중지

### Docker Compose

```bash
docker compose down        # 중지 (데이터 유지)
docker compose down -v     # 중지 + 데이터 삭제
```

---

## 9. 아키텍처

```
[사용자] → [웹 대시보드 :3000]
                 ↓
          [에이전트 API :8000]
                 ↓
    ┌────────────┼────────────┐
    ↓            ↓            ↓
[PostgreSQL] [Slack Bot] [APScheduler]
                 ↓            ↓
           [알림 전송]   [2분마다 로그 수집]
                              ↓
                    [kubectl logs / SSH]
                              ↓
                    [data-pipeline :8001] → [Qwen API] → [MinIO]
```

### LangGraph 에이전트 워크플로우

```
collect_logs → analyze (ReAct) → plan_fix → approval (HITL)
                                                ↓
                                      approve / reject / feedback
                                         ↓         ↓         ↓
                                    apply_fix    END    re-analyze
                                         ↓
                                    build_image → staging → verify → production
                                                                         ↓
                                                              [PR 생성/Merge/유지]
```

---

## 10. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| 로그인 안 됨 | DB 초기화 안 됨 | `docker compose down -v && docker compose up -d` |
| Slack 알림 안 옴 | 토큰 미설정 | `.env`에 SLACK_APP_TOKEN, SLACK_BOT_TOKEN 입력 |
| 에러 감지 안 됨 | 서비스 미등록 | Services 탭에서 서비스 등록 |
| Qwen API 타임아웃 | 모델 응답 느림 | config.yaml의 timeout 값 증가 |
| 승인 후 반응 없음 | v1 에이전트가 실행 중 | 로컬 v1 에이전트 종료 |
| 스테이징 실패 | Secret 없음 | pipeline-staging NS에 Secret/ConfigMap 생성 |
