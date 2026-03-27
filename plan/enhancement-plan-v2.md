# Error Log Agent v2 고도화 계획서

> **목적**: error-log-agent v2의 기능 확장 및 코드 품질 개선을 위한 상세 구현 지시서
>
> **대상 독자**: Claude Code에게 전달하여 순차적으로 구현을 지시하기 위한 문서
>
> **기준 버전**: error-log-agent v2 (LangGraph 기반, K3s + Slack + React 대시보드)
>
> **우선순위**: SSH 테스트 → 코드 품질 개선 → Docker Compose 배포 → 인증/권한

---

## 실행 순서 요약

| 순위 | 항목 | 난이도 | 이유 |
|:---:|------|:---:|------|
| 1 | SSH 원격 로그 수집 테스트 | 하~중 | 공수 적고, 기존 기능 검증이라 리스크 낮음 |
| 2 | 코드 품질 개선 | 중 | 다른 작업의 기반이 되는 내부 품질 개선 |
| 3 | Docker Compose 배포 패키징 | 중 | 외부 공개 전 필수, 4번보다 선행되어야 함 |
| 4 | 사용자 인증 및 권한 관리 | 상 | 가장 공수 크고, 배포 구조 잡힌 뒤에 하는 게 효율적 |

---

## 1. SSH 원격 로그 수집 테스트

### 1.1 배경

`src/log_collector/file_collector.py`에 SSH로 Mac Studio(192.168.50.26)에 접속하여 로그를 읽는 코드가 존재하지만, 아직 실제 환경에서 E2E 테스트가 완료되지 않았다.

### 1.2 검증 항목

#### SSH 연결 테스트

- SSH 키 인증 vs 비밀번호 인증 방식 확인 및 정리
- 연결 타임아웃 설정 확인 (기본값, 권장값)
- Mac Studio(192.168.50.26) → user: `sam` 연결 성공 여부
- 네트워크 단절 시 에러 핸들링 동작 확인

#### 로그 파일 접근 테스트

- 대상 파일: `/Users/sam/dev/Qwen3VL-32b/logs/mlx_server.stderr.log`
- 파일 존재하지 않을 때 에러 처리
- 파일 권한 없을 때 에러 처리
- 파일이 비어있을 때 처리
- 로그가 계속 쓰이고 있는 중(active writing)에 읽기 동작 확인

#### 시간 윈도우 필터링 테스트

- 최근 120초(기본값) 필터링이 실제로 정확히 동작하는지
- 타임존 차이가 있을 때 필터링 정확성
- 로그 타임스탬프 포맷과 파서 호환성 확인

#### 파싱 테스트

- `src/log_collector/parser.py`의 structlog JSON 파싱이 Mac Studio 로그 포맷과 호환되는지
- ERROR/CRITICAL 레벨 필터링(`src/log_collector/filter.py`) 정상 동작 여부
- 비정형 로그(JSON이 아닌 stderr 출력) 처리 방법

### 1.3 구현 지시

```
1. tests/ 디렉토리에 SSH 로그 수집 관련 테스트 파일 생성
   - tests/test_file_collector.py
   - tests/test_ssh_integration.py (실제 환경 E2E)

2. 단위 테스트 (mock 기반)
   - SSH 연결 성공/실패 시나리오
   - 파일 읽기 성공/실패/비어있음 시나리오
   - 시간 윈도우 필터링 정확성
   - 파서 호환성 (다양한 로그 포맷 샘플)

3. 통합 테스트 (실제 Mac Studio 대상)
   - pytest marker로 분리: @pytest.mark.integration
   - SSH 연결 → 파일 읽기 → 파싱 → 필터링 전체 파이프라인
   - 에러 시나리오별 로그 출력 및 복구 확인

4. file_collector.py 개선 사항 (테스트 중 발견되는 이슈 기반)
   - 연결 재시도 로직 추가 (최대 3회, 지수 백오프)
   - 상세 에러 메시지 및 structlog 로깅
   - 파일 접근 불가 시 graceful 처리 (agent 중단 방지)
```

### 1.4 완료 기준

- [ ] 단위 테스트 전체 통과 (mock 기반)
- [ ] 통합 테스트 Mac Studio 대상 성공
- [ ] 에지 케이스(파일 없음, 권한 없음, 연결 끊김, 빈 파일) 처리 확인
- [ ] 연결 재시도 로직 구현 및 테스트

---

## 2. 코드 품질 개선

### 2.1 배경

현재 LangGraph 기반 state machine으로 10개 노드가 구현되어 있으나, 에이전트의 자율성, 에러 핸들링 일관성, 크로스커팅 관심사 처리에 개선 여지가 있다.

### 2.2 개선 항목

#### 2.2.1 LangChain create_react_agent 도입

**현재 상태**: `analyze_code_node`, `plan_fix_node`에서 단순 LLM 호출 (프롬프트 → 응답)

**개선 방향**: Tool 기반 ReAct 에이전트로 전환하여 에이전트가 자율적으로 행동 결정

```
구현 지시:

1. src/tools/ 디렉토리에 에이전트용 Tool 정의
   - read_source_code: 특정 파일/라인 범위의 소스코드 읽기
   - search_related_files: 에러와 관련된 파일 탐색
   - web_search: 기존 Tavily 검색을 Tool로 래핑
   - get_git_history: 최근 커밋 히스토리 조회
   - read_k8s_logs: 추가 로그 조회

2. src/agent/nodes/analyze_code_node.py 수정
   - 기존: ChatOpenAI.invoke(messages) 직접 호출
   - 변경: create_react_agent(llm, tools) 사용
   - 에이전트가 필요에 따라 소스코드 추가 조회, 관련 파일 탐색,
     웹 검색 등을 자율적으로 수행하도록 변경

3. src/agent/nodes/plan_fix_node.py 수정
   - 동일하게 ReAct 에이전트로 전환
   - 수정 계획 수립 시 관련 파일을 직접 탐색하여
     영향 범위를 자율적으로 파악

4. config.yaml에 에이전트 Tool 설정 추가
   - 각 Tool의 활성화/비활성화 설정
   - Tool별 타임아웃 설정
```

#### 2.2.2 미들웨어 레이어 도입

**현재 상태**: HITL 미들웨어만 존재, 로깅/에러핸들링/재시도가 노드마다 제각각

**개선 방향**: 크로스커팅 관심사를 일관되게 처리하는 미들웨어 패턴 도입

```
구현 지시:

1. src/agent/middleware/ 디렉토리 구성
   - __init__.py
   - base.py         # 미들웨어 기본 클래스
   - logging_mw.py   # 노드 실행 전후 structlog 로깅
   - error_mw.py     # 에러 핸들링 + 재시도 로직
   - metrics_mw.py   # 노드별 실행 시간, 성공/실패 메트릭

2. 미들웨어 래퍼 구현
   - 각 LangGraph 노드를 감싸는 데코레이터/래퍼 패턴
   - 실행 전: 시작 시간 기록, 입력 상태 로깅
   - 실행 후: 종료 시간 기록, 출력 상태 로깅, 메트릭 수집
   - 에러 시: 에러 로깅, 재시도 판단, Slack 알림

3. FastAPI 미들웨어 추가 (src/server/app.py)
   - 요청/응답 로깅 미들웨어
   - CORS 미들웨어 (프론트엔드 연동)
   - 요청 시간 측정 미들웨어
```

#### 2.2.3 에러 핸들링 통합

**현재 상태**: PostgreSQL 폴백만 존재, 노드별 에러 처리 비일관적

```
구현 지시:

1. src/agent/nodes/error_handler_node.py 생성
   - 통합 에러 처리 노드
   - 에러 유형별 분류 (일시적/영구적/치명적)
   - 일시적 에러: 재시도 (지수 백오프)
   - 영구적 에러: Slack 알림 후 종료
   - 치명적 에러: 즉시 중단 + 관리자 알림

2. src/agent/graph.py 수정
   - 각 노드에서 에러 발생 시 error_handler_node로 라우팅하는
     conditional edge 추가
   - 에러 핸들러에서 재시도/종료/알림 분기

3. 에러 컨텍스트 보존
   - AgentState에 error_history: list[dict] 필드 추가
   - 에러 발생 시 노드명, 에러 타입, 메시지, 타임스탬프 기록
   - 대시보드에서 에러 히스토리 조회 가능하도록 API 추가
```

### 2.3 완료 기준

- [ ] analyze_code_node, plan_fix_node가 ReAct 에이전트로 동작
- [ ] 미들웨어 체인을 통해 모든 노드에 일관된 로깅/메트릭 적용
- [ ] 에러 핸들러 노드를 통한 통합 에러 처리 동작
- [ ] 기존 테스트 통과 + 새 테스트 추가

---

## 3. Docker Compose 배포 패키징

### 3.1 배경

현재 K8s 매니페스트는 존재하지만, 다른 개발자가 로컬에서 빠르게 실행해볼 수 있는 방법이 없다. `docker compose up` 한 번으로 전체 스택을 띄울 수 있어야 한다.

### 3.2 구현 지시

#### 3.2.1 docker-compose.yml 작성

```
프로젝트 루트에 docker-compose.yml 생성

서비스 구성:
  1. postgres
     - image: postgres:16-alpine
     - volume: pgdata
     - 환경변수: POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
     - healthcheck: pg_isready

  2. minio
     - image: minio/minio:latest
     - volume: minio-data
     - ports: 9000 (API), 9001 (Console)
     - healthcheck: curl

  3. agent (메인 에이전트)
     - build: . (루트 Dockerfile)
     - depends_on: postgres (healthy)
     - ports: 8000
     - env_file: .env
     - environment: DB 연결 정보를 docker 내부 네트워크 주소로 오버라이드

  4. target-service (데이터 파이프라인)
     - build: ./target-source
     - depends_on: postgres (healthy), minio (healthy)
     - ports: 8001
     - env_file: .env

  5. frontend
     - build: ./frontend (별도 Dockerfile 필요)
     - depends_on: agent
     - ports: 3000
     - nginx로 정적 파일 서빙 + API 프록시

networks:
  - log-agent-network (bridge)

volumes:
  - pgdata
  - minio-data
```

#### 3.2.2 프론트엔드 Dockerfile 작성

```
frontend/Dockerfile 생성:
  - Stage 1: node:20-alpine → npm install → npm run build
  - Stage 2: nginx:alpine → 빌드 결과물 복사 → nginx.conf로 API 프록시 설정
```

#### 3.2.3 환경 설정 파일

```
1. .env.example 생성
   - 모든 필수 환경변수를 기본값 또는 placeholder로 기재
   - 각 변수에 주석으로 설명 추가
   - 민감 정보(API 키)는 YOUR_xxx_HERE 형태로

2. config.yaml 수정
   - Docker 환경과 K8s 환경을 분기하는 설정 추가
   - 환경변수 기반으로 자동 감지 또는 DEPLOY_MODE 변수 활용
```

#### 3.2.4 사용 가이드 작성

```
docs/quickstart.md 생성:

  1. 사전 요구사항
     - Docker, Docker Compose v2 설치
     - OpenAI API 키
     - (선택) Slack Bot 토큰
     - (선택) Tavily API 키

  2. 빠른 시작 (5분 내 실행)
     - git clone
     - cp .env.example .env → API 키 입력
     - docker compose up -d
     - http://localhost:3000 접속

  3. 설정 가이드
     - 서비스 등록 방법 (웹 대시보드에서)
     - Slack Bot 연동 방법
     - SSH 원격 로그 소스 추가 방법
     - 로그 수집 주기 변경 방법

  4. 아키텍처 설명
     - 전체 서비스 구성도 (ASCII 또는 Mermaid)
     - 데이터 흐름 설명
     - LangGraph 에이전트 워크플로우

  5. 트러블슈팅
     - 자주 발생하는 에러와 해결 방법
     - 로그 확인 방법 (docker compose logs)
```

### 3.3 완료 기준

- [ ] `docker compose up -d`로 전체 스택 정상 기동
- [ ] 프론트엔드에서 API 호출 정상 동작
- [ ] .env.example만으로 필수 설정 파악 가능
- [ ] quickstart.md 가이드대로 따라하면 5분 내 실행 가능
- [ ] 각 서비스 healthcheck 통과

---

## 4. 사용자 인증 및 권한 관리

### 4.1 배경

현재 API 엔드포인트(`/api/dashboard/*`)에 인증이 없어 누구나 접근 가능하다. 서비스 추가/삭제, fix 승인 등 민감한 작업에 대한 접근 제어가 필요하다.

### 4.2 역할 정의

| 역할 | 대시보드 열람 | 서비스 관리 | Fix 승인/거절 | 사용자 관리 |
|------|:---:|:---:|:---:|:---:|
| Viewer | O | X | X | X |
| Operator | O | O | O | X |
| Admin | O | O | O | O |

### 4.3 구현 지시

#### 4.3.1 백엔드 인증 (FastAPI)

```
구현 지시:

1. 의존성 추가 (pyproject.toml)
   - fastapi-users[sqlalchemy] >= 13.0.0
   - python-jose[cryptography] >= 3.3.0
   - passlib[bcrypt] >= 1.7.4

2. src/auth/ 디렉토리 구성
   - __init__.py
   - models.py      # User, Role SQLAlchemy 모델
   - schemas.py     # UserCreate, UserRead, UserUpdate Pydantic 스키마
   - manager.py     # UserManager (fastapi-users)
   - backend.py     # JWTStrategy + CookieTransport
   - deps.py        # current_active_user, require_role 의존성

3. DB 마이그레이션
   - users 테이블: id, email, hashed_password, role, is_active, created_at
   - PostgreSQL에 테이블 생성 (기존 error_log_agent DB에 추가)

4. API 엔드포인트 추가 (src/server/routes.py 또는 src/auth/routes.py)
   - POST /api/auth/register    # 회원가입
   - POST /api/auth/login       # 로그인 (JWT 발급)
   - POST /api/auth/logout      # 로그아웃
   - GET  /api/auth/me          # 현재 사용자 정보
   - GET  /api/auth/users       # 사용자 목록 (Admin만)
   - PUT  /api/auth/users/{id}  # 역할 변경 (Admin만)

5. 기존 라우트에 권한 적용
   - GET 엔드포인트: Viewer 이상
   - POST/PUT/DELETE 서비스 관리: Operator 이상
   - fix 승인/거절: Operator 이상
   - 사용자 관리: Admin만

6. 초기 Admin 계정
   - 환경변수로 초기 Admin 이메일/비밀번호 설정
   - 앱 시작 시 Admin 계정 없으면 자동 생성
```

#### 4.3.2 프론트엔드 인증 (React)

```
구현 지시:

1. 새 페이지 추가
   - frontend/src/pages/Login.jsx      # 로그인 페이지
   - frontend/src/pages/Register.jsx   # 회원가입 페이지
   - frontend/src/pages/UserManage.jsx # 사용자 관리 (Admin)

2. 인증 컨텍스트
   - frontend/src/contexts/AuthContext.jsx
   - JWT 토큰 관리 (메모리 + httpOnly cookie)
   - 로그인 상태 전역 관리
   - 자동 토큰 갱신

3. 라우트 가드
   - frontend/src/components/ProtectedRoute.jsx
   - 미인증 → 로그인 페이지로 리다이렉트
   - 권한 부족 → 403 페이지 표시

4. API 클라이언트 수정 (frontend/src/api.js)
   - 모든 요청에 Authorization 헤더 추가
   - 401 응답 시 로그인 페이지로 리다이렉트
   - 토큰 만료 시 자동 갱신 시도

5. 네비게이션 수정
   - 로그인 상태에 따른 메뉴 표시/숨김
   - 역할에 따른 메뉴 필터링
   - 로그아웃 버튼 추가
```

#### 4.3.3 Slack 권한 연동

```
구현 지시:

1. Slack 사용자 ↔ 시스템 사용자 매핑
   - users 테이블에 slack_user_id 필드 추가
   - Slack에서 fix 승인 시 해당 slack_user_id로 시스템 사용자 조회
   - 매핑된 사용자의 역할이 Operator 이상인지 확인

2. 미등록 Slack 사용자 처리
   - 매핑되지 않은 Slack 사용자의 승인/거절 → 거부 + 안내 메시지
   - "웹 대시보드에서 계정을 연동해주세요" 메시지 전송
```

### 4.4 완료 기준

- [ ] 회원가입/로그인/로그아웃 정상 동작
- [ ] JWT 기반 API 인증 전체 라우트 적용
- [ ] 역할별 접근 제어 동작 (Viewer/Operator/Admin)
- [ ] 프론트엔드 라우트 가드 및 권한별 UI 분기
- [ ] Slack 사용자-시스템 사용자 매핑 동작
- [ ] 초기 Admin 계정 자동 생성
- [ ] 기존 기능 회귀 테스트 통과

---

## 참고: 현재 프로젝트 기술 스택

| 구성 | 기술 |
|------|------|
| 에이전트 프레임워크 | LangGraph 0.4.0+ |
| LLM | OpenAI GPT-4o-mini |
| API 서버 | FastAPI 0.115.0+ |
| 로그 수집 | kubectl logs + SSH (paramiko) |
| 스케줄러 | APScheduler 3.10.0 |
| 상태 저장 | PostgreSQL (LangGraph Checkpointer) |
| Slack | Slack Bolt async (Socket Mode) |
| CI/CD | Git → Harbor → K3s 배포 |
| 프론트엔드 | React 19 + Vite + Recharts |
| 웹 검색 | Tavily API |
