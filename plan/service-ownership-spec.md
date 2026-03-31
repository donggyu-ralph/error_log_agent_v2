# 서비스 소유권 및 멤버 관리 기획서

> **목적**: 서비스별 소유자/멤버 관리, Slack 채널 자동 생성, 권한 기반 에러 알림 분리
>
> **선행 조건**: Enhancement #4 (사용자 인증/권한) 완료

---

## 1. 개요

### 1.1 현재 문제
- 모든 사용자가 모든 서비스의 에러를 볼 수 있음
- Slack 알림이 단일 채널(#error-log-agent)에 전송
- 서비스 중복 등록 가능, 담당자 구분 없음
- 승인/거절 권한이 서비스별로 분리되지 않음

### 1.2 목표
- 서비스별 Owner/Member 역할 관리
- Slack 채널 자동 생성/멤버 관리
- 대시보드에서 내 서비스만 표시
- 에러 알림을 해당 서비스 담당자에게만 전송

---

## 2. 데이터 모델

### 2.1 DB 스키마

```sql
-- 서비스 멤버 테이블
CREATE TABLE service_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_id UUID NOT NULL REFERENCES monitored_services(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL DEFAULT 'member',  -- owner, member
    slack_channel_id VARCHAR(100),                -- 서비스 전용 Slack 채널
    invited_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(service_id, user_id)
);

-- monitored_services에 slack_channel_id 추가
ALTER TABLE monitored_services ADD COLUMN slack_channel_id VARCHAR(100);
ALTER TABLE monitored_services ADD COLUMN created_by UUID REFERENCES users(id);

CREATE INDEX idx_service_members_user ON service_members(user_id);
CREATE INDEX idx_service_members_service ON service_members(service_id);
```

### 2.2 역할 정의

| 역할 | 서비스 설정 변경 | 멤버 초대/제거 | 에러 알림 수신 | 승인/거절 | 서비스 삭제 |
|------|:---:|:---:|:---:|:---:|:---:|
| Owner | O | O | O | O | O |
| Member | X | X | O | O | X |
| 비멤버 | X | X | X | X | X |

---

## 3. API 설계

### 3.1 서비스 등록 (기존 수정)

```
POST /api/dashboard/services
Body: { name, source_type, namespace, label_selector, ... }
Auth: Operator 이상
동작:
  1. monitored_services에 저장 (created_by = 현재 사용자)
  2. service_members에 owner로 추가
  3. Slack 채널 생성: #svc-{service_name}
  4. 등록자를 Slack 채널에 추가
```

### 3.2 멤버 관리

```
GET    /api/services/{service_id}/members          — 멤버 목록
POST   /api/services/{service_id}/members          — 멤버 초대
       Body: { email: "user@atdev.co.kr" }
       동작: user 조회 → service_members 추가 → Slack 채널 초대
DELETE /api/services/{service_id}/members/{user_id} — 멤버 제거
       동작: service_members 삭제 → Slack 채널 제거
```

### 3.3 대시보드 필터링

```
GET /api/dashboard/summary    — 내 서비스만
GET /api/dashboard/errors     — 내 서비스 에러만
GET /api/dashboard/history    — 내 서비스 수정 이력만
GET /api/dashboard/services   — 내가 속한 서비스만
```

모든 목록 API에 `user_id` 기반 필터 적용.
Admin은 모든 서비스 조회 가능.

---

## 4. Slack 연동

### 4.1 채널 자동 생성

```
서비스 등록 시:
  1. Slack API: conversations.create(name="svc-{service_name}")
  2. channel_id를 monitored_services.slack_channel_id에 저장
  3. 등록자를 채널에 초대: conversations.invite
```

### 4.2 에러 알림 라우팅

```
기존: #error-log-agent 단일 채널에 전송
변경: 에러 발생 서비스의 slack_channel_id로 전송

에러 감지 → 서비스명 확인 → monitored_services에서 slack_channel_id 조회 → 해당 채널에 전송
```

### 4.3 멤버 초대/제거

```
멤버 초대 시:
  1. users 테이블에서 slack_user_id 조회
  2. conversations.invite(channel=slack_channel_id, users=slack_user_id)

멤버 제거 시:
  1. conversations.kick(channel=slack_channel_id, user=slack_user_id)
```

### 4.4 승인 권한

```
Slack에서 승인/거절 버튼 클릭 시:
  1. 클릭한 사용자의 slack_user_id 확인
  2. service_members에서 해당 서비스의 멤버인지 확인
  3. 멤버가 아니면 → "이 서비스에 대한 권한이 없습니다" 메시지
  4. 멤버이면 → 승인/거절 처리
```

---

## 5. 프론트엔드

### 5.1 서비스 상세 페이지 (신규)

```
/services/{id}

섹션:
  1. 서비스 정보 (이름, 소스 타입, 네임스페이스 등)
  2. 멤버 목록
     - Owner 표시
     - [초대] 버튼 (Owner만)
     - [제거] 버튼 (Owner만, 자기 자신 제외)
  3. 최근 에러 (이 서비스만)
  4. Slack 채널 링크
```

### 5.2 대시보드 수정

```
- 기존: 모든 에러 표시
- 변경: 내가 속한 서비스 에러만 표시
- Admin 토글: "전체 보기" / "내 서비스만" 스위치
```

### 5.3 서비스 목록 수정

```
- 기존: 전체 서비스 목록
- 변경: 내가 속한 서비스만 (Owner/Member)
- 각 서비스에 멤버 수 표시
- Owner인 서비스에 [설정] 버튼
```

---

## 6. 구현 순서

| 순위 | 작업 | 설명 |
|:---:|------|------|
| 1 | DB 스키마 | service_members 테이블, monitored_services 컬럼 추가 |
| 2 | 서비스 등록 수정 | Owner 자동 등록, created_by 저장 |
| 3 | 멤버 관리 API | 초대/목록/제거 엔드포인트 |
| 4 | 대시보드 필터링 | 내 서비스 에러만 표시 |
| 5 | Slack 채널 자동 생성 | conversations.create + invite |
| 6 | 에러 알림 라우팅 | 서비스별 채널로 전송 |
| 7 | Slack 승인 권한 | 멤버 확인 후 승인/거절 |
| 8 | 프론트엔드 | 서비스 상세, 멤버 관리, 필터링 |
| 9 | 단위 테스트 | 각 단계별 필수 |

---

## 7. 완료 기준

- [ ] 서비스 등록 시 Owner 자동 지정 + Slack 채널 생성
- [ ] 멤버 초대/제거 → Slack 채널 자동 반영
- [ ] 대시보드: 내 서비스 에러만 표시
- [ ] Slack 알림: 서비스별 채널로 전송
- [ ] 승인/거절: 해당 서비스 멤버만 가능
- [ ] Admin: 모든 서비스 조회 가능
- [ ] 단위 테스트 통과
