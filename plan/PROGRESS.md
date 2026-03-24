# Error Log Agent v2 - 진행 상황

> 최종 업데이트: 2026-03-24

---

## 1. 프로젝트 구성

| 프로젝트 | GitHub | 설명 |
|----------|--------|------|
| data-pipeline-service | [pipeline_target_service](https://github.com/donggyu-ralph/pipeline_target_service) | 모니터링 대상 서비스 (FastAPI + Qwen VLM 분석) |
| error-log-agent-v2 | [error_log_agent_v2](https://github.com/donggyu-ralph/error_log_agent_v2) | 에이전트 (LangGraph + Slack + K8s 배포) |

---

## 2. 인프라 현황

### K3s 클러스터
| 노드 | IP | 역할 |
|------|-----|------|
| atdev-server-00 | 192.168.50.10 | Control Plane + Harbor + Docker |
| atdev-server-01 | 192.168.50.11 | Worker |
| atdev-server-02 | 192.168.50.12 | Control Plane |
| atdev-server-03 | 192.168.50.13 | Control Plane |

### 배포 상태
| 서비스 | 네임스페이스 | 이미지 | 상태 |
|--------|-------------|--------|------|
| data-pipeline | pipeline | `192.168.50.10:8880/custom/data-pipeline:v5` | Running |
| error-log-agent | pipeline | `192.168.50.10:8880/custom/error-log-agent:v32` | Running |
| data-pipeline (staging) | pipeline-staging | 에이전트가 동적 배포 | Secret/ConfigMap 설정 완료 |

### 외부 서비스
| 서비스 | 주소 | 상태 |
|--------|------|------|
| Harbor | 192.168.50.10:8880 | 정상 |
| PostgreSQL | data NS (postgres.data.svc) | 정상 (trust 인증) |
| MinIO | data NS (minio.data.svc:9000) | 정상 |
| Qwen VLM API | https://192.168.50.26:32000 | 정상 (HTTPS, self-signed cert) |
| Cloudflare Tunnel | agent.atdev.ai | 정상 (Access 이메일 인증 적용) |

---

## 3. 기능 구현 현황

### 핵심 기능
| 기능 | 상태 | 비고 |
|------|------|------|
| 로그 수집 (kubectl logs, 2분 주기) | ✅ 완료 | APScheduler |
| 에러 감지 + 파싱 | ✅ 완료 | structlog dict 파싱, traceback 추출 |
| GPT-4o-mini 분석 | ✅ 완료 | response_format: json_object |
| 수정 계획 생성 | ✅ 완료 | 상대 경로 강제, 순수 JSON |
| Slack 보고서 전송 | ✅ 완료 | Block Kit, 에러 타입/위치/traceback |
| Slack 승인/거절 | ✅ 완료 | 버튼 비활성화 포함 |
| Slack 피드백 | ✅ 완료 | 모달 입력 → 재분석 → 새 보고서 |
| 코드 수정 + Git 커밋 | ✅ 완료 | LLM 코드 생성, 경로 정규화 |
| GitHub 브랜치 push | ✅ 완료 | 자동 push |
| Docker 이미지 빌드 | ✅ 완료 | 동적 빌드 Pod (Docker 소켓 마운트) |
| Harbor push | ✅ 완료 | 자동 push |
| 스테이징 배포 + 검증 | ✅ 완료 | Secret/ConfigMap 설정 완료 |
| 프로덕션 배포 | ✅ 완료 | kubectl set image |
| Slack PR 생성/Merge/브랜치 유지 | ✅ 완료 | GitHub API 연동 |
| 웹 대시보드 | ✅ 완료 | React + Vite |
| Cloudflare Tunnel + Access | ✅ 완료 | 이메일 인증 |

### HITL Middleware
| 항목 | 상태 | 비고 |
|------|------|------|
| LangGraph interrupt/resume | ✅ 완료 | PostgreSQL checkpointer (fallback: MemorySaver) |
| 재사용 가능한 middleware 패턴 | ✅ 완료 | `src/agent/middleware.py` |
| astream_events 실시간 알림 | ✅ 완료 | 각 노드 시작 시 Slack 알림 |
| 피드백 → 재분석 → 새 보고서 | ✅ 완료 | 그래프 re-interrupt 감지 |

### 웹 대시보드
| 페이지 | 상태 | 기능 |
|--------|------|------|
| Dashboard (/) | ✅ | 에러 타임라인 차트, 타입별 통계, stat 카드 (클릭 → 페이지 이동) |
| Error Logs (/errors) | ✅ | 에러 목록, 서비스 필터, 상세 보기 |
| Error Detail (/errors/:id) | ✅ | traceback, 파일 위치 |
| Fix History (/history) | ✅ | 수정 이력, 행 클릭 → 상세 패널 (분석, diff, 배포 상태) |
| Services (/services) | ✅ | 모니터링 대상 서비스 관리 |

---

## 4. 아키텍처

### LangGraph 그래프 (10 노드)
```
collect_logs → has_errors? → analyze_code → plan_fix → request_approval (HITL interrupt)
                                                              ↓
                                                     approve / reject / feedback
                                                        ↓         ↓         ↓
                                                   apply_fix    END    analyze_code (재분석)
                                                        ↓
                                                   build_image (동적 빌드 Pod)
                                                        ↓
                                                   deploy_staging
                                                        ↓
                                                   verify_staging → unhealthy → END
                                                        ↓ healthy
                                                   deploy_production
                                                        ↓
                                                   monitor → recurring → analyze_code
                                                        ↓ resolved
                                                       END
```

### 이미지 빌드 방식
```
에이전트 Pod → tar 생성 → 동적 빌드 Pod 생성 (Docker 소켓 마운트)
                              → tar 복사 → docker build → Harbor push
                              → 빌드 Pod 삭제
```

### Slack 흐름
```
[에러 보고서] → [승인] → 코드 수정 중... → 빌드 중... → 스테이징 중... → 프로덕션 배포 완료!
                                                                              ↓
                                                                   [PR 생성] [Merge] [브랜치 유지]

[에러 보고서] → [피드백] → 모달 입력 → 재분석 → [새 보고서] → [승인] → ...

[에러 보고서] → [거절] → 종료
```

---

## 5. 해결한 주요 이슈

| # | 이슈 | 원인 | 해결 |
|---|------|------|------|
| 1 | pyproject.toml build-backend 오류 | `setuptools.backends._legacy` 없음 | `setuptools.build_meta`로 변경 |
| 2 | Pydantic Settings extra fields | `.env`의 변수가 Settings에 extra로 인식 | `extra: "ignore"` 추가 |
| 3 | PostgreSQL 인증 실패 | PG13 + psycopg2 SCRAM 호환 문제 | trust 인증으로 전환 |
| 4 | Traceback 파서 누락 | 마지막 예외 줄 미포함 | TRACEBACK_PATTERN 수정 |
| 5 | structlog dict 메시지 파싱 | 에러 타입/위치 추출 불가 | `_parse_structlog_message` 구현 |
| 6 | Qwen API 400 Bad Request | HTTP로 HTTPS 포트 접속 | `http://` → `https://` + `verify=False` |
| 7 | UploadFile closed | asyncio.create_task에서 파일 핸들 닫힘 | 미리 content 읽기 |
| 8 | LLM JSON 파싱 실패 | 코드블록으로 감싼 JSON 반환 | `response_format: json_object` 강제 |
| 9 | 코드 수정 경로 불일치 | LLM이 `/app/src/...` 절대 경로 반환 | 경로 정규화 로직 추가 |
| 10 | Liveness probe 실패 | subprocess 블로킹으로 health 무응답 | `asyncio.to_thread` + `failureThreshold: 10` |
| 11 | Slack v1 이벤트 가로채기 | 로컬 v1 에이전트가 Socket Mode 세션 선점 | v1 종료 |
| 12 | 승인 정보 Pod 재시작 시 소실 | 인메모리 `_pending_approvals` | DB 기반 조회 + PostgreSQL checkpointer |
| 13 | RBAC 권한 부족 | deployments create/watch 없음 | ClusterRole에 권한 추가 |
| 14 | 스테이징 검증 항상 실패 | pipeline-staging NS에 Secret 없음 | Secret/ConfigMap 복사 |
| 15 | 피드백 모달 unhandled | `@app.view("")`가 callback_id 매칭 안 됨 | `re.compile(r"feedback_modal_.*")` |

---

## 6. 미완료 / 개선 필요 사항

### 단기
| 항목 | 우선순위 | 설명 |
|------|---------|------|
| 웹 페이징 처리 | 높음 | Error Logs, Fix History 20개씩 페이징 |
| Qwen API 타임아웃 | 중간 | config.yaml timeout 300초로 증가 (현재 120초) |
| Mac Studio SSH 로그 수집 | 낮음 | SSH 키 인증 설정 필요 |

### 장기
| 항목 | 설명 |
|------|------|
| PostgreSQL checkpointer 안정화 | psycopg v3 호환 확인, fallback 시 MemorySaver |
| 대시보드 자동 새로고침 | polling 또는 WebSocket |
| 코드 수정 품질 향상 | LLM에 더 많은 컨텍스트 (API 스펙, 테스트 코드) 제공 |
| 멀티 서비스 모니터링 | 여러 타겟 서비스 동시 모니터링 |
| Airflow DAG 모니터링 | 기획서 Phase 11 향후 확장 |

---

## 7. 버전 히스토리 (주요)

| 버전 | 날짜 | 내용 |
|------|------|------|
| v1~v4 | 03-24 | 초기 배포, PostgreSQL trust 인증, HTTPS Qwen 수정 |
| v5~v10 | 03-24 | Slack 승인 흐름, 버튼 비활성화, DB 기반 승인 |
| v11~v18 | 03-24 | 프론트엔드 통합, GitHub 연동, JSON 파싱 강화 |
| v19~v22 | 03-24 | GitHub PR/Merge 버튼, Fix History 상세, 차트 개선 |
| v23~v27 | 03-24 | HITL middleware 리팩토링, PostgreSQL checkpointer, astream_events |
| v28~v32 | 03-24 | non-blocking deployer, RBAC watch, 피드백 re-interrupt, 스테이징 Secret |
