"""Slack Block Kit message builder."""

SAFE_TEXT_LENGTH = 2900  # Slack block text limit is ~3000


def format_file_location(error_info: dict) -> str:
    """Format file location for display."""
    file_path = error_info.get("file_path")
    line_number = error_info.get("line_number")

    if file_path and line_number:
        return f"`{file_path}:{line_number}`"
    elif file_path:
        return f"`{file_path}`"
    else:
        return "_위치 정보 없음 (traceback 미포함)_"


def build_error_report(
    thread_id: str,
    error_logs: list[dict],
    analysis: str,
    fix_plan: dict,
) -> list[dict]:
    """Build Slack blocks for error detection report."""
    blocks = []

    # Header
    blocks.append({
        "type": "header",
        "text": {"type": "plain_text", "text": "[ALERT] Error Log Agent v2 - 에러 감지"},
    })
    blocks.append({"type": "divider"})

    # Error summary
    if error_logs:
        err = error_logs[0]
        svc = err.get("service_name", "unknown")
        ns = err.get("namespace", "")
        pod = err.get("pod_name", "")

        # Format timestamp
        ts = err.get("timestamp", "unknown")
        if isinstance(ts, str):
            ts = ts.replace(",", ".")

        info_text = f"*서비스:* `{svc}`\n"
        if ns:
            info_text += f"*네임스페이스:* `{ns}`\n"
        if pod:
            info_text += f"*Pod:* `{pod}`\n"
        info_text += f"*감지 시각:* {ts}\n"
        info_text += f"*에러 타입:* `{err.get('error_type') or '알 수 없음'}`\n"
        info_text += f"*발생 위치:* {format_file_location(err)}\n"

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": info_text},
        })

        # Error message - clean up for readability
        raw_msg = err.get("message", "Unknown")
        # If it looks like a structlog dict, extract the error part
        if raw_msg.startswith("{") or raw_msg.startswith("{'"):
            try:
                import ast
                data = ast.literal_eval(raw_msg)
                if isinstance(data, dict):
                    error_part = data.get("error", raw_msg)
                    raw_msg = error_part.split("\nFor more information")[0].strip()
            except (ValueError, SyntaxError):
                pass

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*에러 메시지:*\n```{raw_msg}```"},
        })

        # Traceback
        traceback_text = err.get("traceback")
        if traceback_text:
            _append_code_blocks(blocks, "*Traceback:*", traceback_text)

    blocks.append({"type": "divider"})

    # Analysis
    if analysis:
        analysis_text = analysis[:SAFE_TEXT_LENGTH]
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*분석 결과:*\n{analysis_text}"},
        })

    # Fix plan
    if fix_plan:
        plan_text = f"*수정 계획:*\n"
        plan_text += f"• *요약:* {fix_plan.get('summary', '')}\n"
        plan_text += f"• *근본 원인:* {fix_plan.get('root_cause', '')}\n"
        plan_text += f"• *위험도:* {fix_plan.get('estimated_risk', 'unknown')}\n"

        target_files = fix_plan.get("target_files", [])
        if target_files:
            plan_text += f"• *수정 대상 파일:*\n"
            for tf in target_files:
                plan_text += f"  - `{tf.get('file_path', '')}`: {tf.get('changes_description', '')}\n"

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": plan_text[:SAFE_TEXT_LENGTH]},
        })

        # Diff preview
        if target_files and target_files[0].get("diff_preview") and target_files[0]["diff_preview"] != "N/A":
            _append_code_blocks(blocks, "*변경 미리보기:*", target_files[0]["diff_preview"], lang="diff")

    blocks.append({"type": "divider"})

    # Action buttons
    blocks.append({
        "type": "actions",
        "block_id": f"approval_{thread_id}",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "승인"},
                "style": "primary",
                "action_id": "approve_fix",
                "value": thread_id,
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "거절"},
                "style": "danger",
                "action_id": "reject_fix",
                "value": thread_id,
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "피드백"},
                "action_id": "feedback_fix",
                "value": thread_id,
            },
        ],
    })

    return blocks


def build_deploy_report(
    thread_id: str,
    error_logs: list[dict],
    fix_plan: dict,
    deployment: dict,
    staging_result: str,
    git_branch: str = None,
    git_commit: str = None,
    modified_files: list[str] = None,
) -> list[dict]:
    """Build Slack blocks for deployment completion report."""
    blocks = []

    blocks.append({
        "type": "header",
        "text": {"type": "plain_text", "text": "[DEPLOY] Error Log Agent v2 - 배포 완료"},
    })
    blocks.append({"type": "divider"})

    err = error_logs[0] if error_logs else {}
    info_text = f"*서비스:* {err.get('service_name', 'unknown')}\n"
    info_text += f"*수정 에러:* {err.get('error_type', 'Unknown')} ({err.get('message', '')[:100]})\n\n"

    if git_branch:
        info_text += f"*Git:* {git_branch}"
        if git_commit:
            info_text += f" ({git_commit[:8]})"
        info_text += "\n"

    if deployment:
        info_text += f"*이미지:* {deployment.get('harbor_image', '')}\n\n"
        info_text += f"*스테이징 검증:* {'통과' if staging_result == 'healthy' else '실패'}\n"
        info_text += f"*프로덕션 배포:* 완료\n"

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": info_text},
    })

    # Modified files
    if modified_files:
        files_text = "*수정된 파일 목록:*\n" + "\n".join(f"• `{f}`" for f in modified_files)
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": files_text[:SAFE_TEXT_LENGTH]},
        })

    blocks.append({"type": "divider"})

    # Rollback button
    if deployment:
        blocks.append({
            "type": "actions",
            "block_id": f"deploy_{thread_id}",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "롤백"},
                    "style": "danger",
                    "action_id": "rollback_deploy",
                    "value": thread_id,
                },
            ],
        })

    return blocks


def _append_code_blocks(blocks: list, header: str, code: str, lang: str = "") -> None:
    """Append code block(s), auto-splitting if too long."""
    prefix = f"{header}\n```{lang}\n"
    suffix = "```"
    max_content = SAFE_TEXT_LENGTH - len(prefix) - len(suffix)

    if len(code) <= max_content:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"{prefix}{code}{suffix}"},
        })
    else:
        # First block with header
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"{prefix}{code[:max_content]}{suffix}"},
        })
        # Remaining blocks
        remaining = code[max_content:]
        while remaining:
            chunk = remaining[:SAFE_TEXT_LENGTH - 6]
            remaining = remaining[SAFE_TEXT_LENGTH - 6:]
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"```{chunk}```"},
            })
