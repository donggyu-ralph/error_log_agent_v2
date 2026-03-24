"""Slack interactive message handlers.

After refactoring:
- Uses LangGraph's interrupt/resume properly
- Graph state persisted in PostgreSQL checkpointer
- On approval, resumes the graph with Command(resume=feedback)
- Graph automatically continues: apply_fix → build → staging → production
"""
import asyncio
from slack_bolt.async_app import AsyncApp

from src.config.logging_config import get_logger

logger = get_logger(__name__)


async def _disable_buttons(client, body, status_text: str):
    """Replace action buttons with a status message."""
    original_message = body.get("message", {})
    channel = body.get("channel", {}).get("id") or body.get("channel")
    ts = original_message.get("ts")
    if not channel or not ts:
        return

    new_blocks = []
    for block in original_message.get("blocks", []):
        if block.get("type") == "actions":
            new_blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": status_text},
            })
        else:
            new_blocks.append(block)

    try:
        await client.chat_update(
            channel=channel, ts=ts, blocks=new_blocks,
            text=original_message.get("text", ""),
        )
    except Exception as e:
        logger.warning("button_disable_failed", error=str(e))


def register_handlers(app: AsyncApp) -> None:

    @app.action("approve_fix")
    async def handle_approve(ack, body, say, client):
        await ack()
        thread_id = body["actions"][0]["value"]
        user = body["user"]["username"]

        logger.info("fix_approved", thread_id=thread_id, user=user)
        await _disable_buttons(client, body, f":white_check_mark: *승인됨* by @{user}")
        await say("코드 수정을 시작합니다. 진행 상황은 이 채널에 보고됩니다.")

        # Resume graph in background (non-blocking)
        asyncio.create_task(
            _resume_graph(thread_id, {"action": "approve", "user": user}, say)
        )

    @app.action("reject_fix")
    async def handle_reject(ack, body, say, client):
        await ack()
        thread_id = body["actions"][0]["value"]
        user = body["user"]["username"]

        logger.info("fix_rejected", thread_id=thread_id, user=user)
        await _disable_buttons(client, body, f":x: *거절됨* by @{user}")

        asyncio.create_task(
            _resume_graph(thread_id, {"action": "reject", "user": user}, say)
        )

    @app.action("feedback_fix")
    async def handle_feedback(ack, body, client):
        await ack()
        thread_id = body["actions"][0]["value"]
        await client.views_open(
            trigger_id=body["trigger_id"],
            view={
                "type": "modal",
                "callback_id": f"feedback_modal_{thread_id}",
                "title": {"type": "plain_text", "text": "피드백 입력"},
                "submit": {"type": "plain_text", "text": "전송"},
                "blocks": [{
                    "type": "input",
                    "block_id": "feedback_input",
                    "label": {"type": "plain_text", "text": "수정 방향에 대한 피드백을 입력하세요"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "feedback_text",
                        "multiline": True,
                    },
                }],
            },
        )

    @app.view("")
    async def handle_feedback_submit(ack, body, view, client):
        await ack()
        callback_id = view["callback_id"]
        if not callback_id.startswith("feedback_modal_"):
            return
        thread_id = callback_id.replace("feedback_modal_", "")
        user = body["user"]["username"]
        feedback_text = view["state"]["values"]["feedback_input"]["feedback_text"]["value"]

        logger.info("feedback_received", thread_id=thread_id, feedback=feedback_text[:100])

        # Post feedback to channel
        from src.config.settings import get_settings
        from src.slack.bot import get_slack_app
        settings = get_settings()
        slack_app = get_slack_app()
        await slack_app.client.chat_postMessage(
            channel=settings.slack.channel,
            text=f":speech_balloon: *피드백* by @{user}: {feedback_text}",
        )

        asyncio.create_task(
            _resume_graph(thread_id, {
                "action": "feedback",
                "user": user,
                "message": feedback_text,
            })
        )

    @app.action("create_pr")
    async def handle_create_pr(ack, body, say, client):
        await ack()
        value = body["actions"][0]["value"]
        thread_id, branch = value.split("|", 1)
        user = body["user"]["username"]
        await _disable_buttons(client, body, f":memo: *PR 생성 요청됨* by @{user}")

        result = await _github_create_pr(branch)
        if result:
            await say(f":white_check_mark: PR 생성 완료: {result}")
        else:
            await say(":warning: PR 생성 실패. GitHub에서 직접 생성해주세요.")

    @app.action("merge_branch")
    async def handle_merge(ack, body, say, client):
        await ack()
        value = body["actions"][0]["value"]
        thread_id, branch = value.split("|", 1)
        user = body["user"]["username"]
        await _disable_buttons(client, body, f":twisted_rightwards_arrows: *Merge 요청됨* by @{user}")

        success, msg = await _github_merge_branch(branch)
        if success:
            await say(f":white_check_mark: `{branch}`가 `main`에 merge되었습니다.")
        else:
            await say(f":warning: {msg}")

    @app.action("keep_branch")
    async def handle_keep(ack, body, say, client):
        await ack()
        value = body["actions"][0]["value"]
        thread_id, branch = value.split("|", 1)
        user = body["user"]["username"]
        await _disable_buttons(client, body, f":bookmark: *브랜치 유지* by @{user}")
        await say(f"브랜치 `{branch}`를 유지합니다.")

    @app.action("rollback_deploy")
    async def handle_rollback(ack, body, say, client):
        await ack()
        thread_id = body["actions"][0]["value"]
        user = body["user"]["username"]
        await _disable_buttons(client, body, f":warning: *롤백 요청됨* by @{user}")

        from src.deployer.rollback import rollback_deployment
        # TODO: get deployment info from DB
        await say("롤백은 수동으로 진행해주세요: `kubectl rollout undo deployment/data-pipeline -n pipeline`")

    @app.event("app_mention")
    async def handle_mention(event, say):
        text = event.get("text", "").lower()
        if "상태" in text or "status" in text:
            await say("에이전트 상태: 실행 중\n대시보드: https://agent.atdev.ai")
        elif "통계" in text or "stats" in text:
            await say("대시보드에서 확인: https://agent.atdev.ai")
        else:
            await say("사용 가능한 명령: `상태`, `통계`")


async def _resume_graph(thread_id: str, feedback: dict, say=None) -> None:
    """Resume the LangGraph agent with human feedback.

    This is the core of the HITL pattern:
    1. The graph was interrupted at request_approval node
    2. Graph state is saved in PostgreSQL checkpointer
    3. We resume with Command(resume=feedback)
    4. Graph continues automatically: apply_fix → build → staging → production
    """
    from langgraph.types import Command
    from src.agent.graph import get_agent
    from src.server.scheduler import _db

    agent = get_agent()
    config = {"configurable": {"thread_id": thread_id}}

    # Update DB
    if _db:
        try:
            history = await _db.list_fix_history(limit=20)
            for h in history:
                if h.get("thread_id") == thread_id:
                    await _db.update_fix_history(str(h["id"]), action=feedback.get("action"))
                    break
        except Exception as e:
            logger.error("db_update_failed", error=str(e))

    # Verify graph is actually interrupted
    try:
        state = agent.get_state(config)
        if not state.next:
            logger.warning("graph_not_interrupted", thread_id=thread_id)
            if say:
                await say(":warning: 이미 처리되었거나 만료된 요청입니다.")
            return
    except Exception as e:
        logger.error("graph_state_check_failed", thread_id=thread_id, error=str(e))
        if say:
            await say(f":warning: 그래프 상태 확인 실패: {str(e)[:200]}")
        return

    # Resume the graph — it continues from where interrupt() paused
    try:
        logger.info("resuming_graph", thread_id=thread_id, action=feedback.get("action"))

        if say:
            await say(":gear: 에이전트가 작업을 재개합니다...")

        # Resume the graph — continues from where interrupt() paused
        from langgraph.types import Command
        result = await agent.ainvoke(Command(resume=feedback), config=config)

        logger.info("graph_resumed_completed", thread_id=thread_id)

        # Report results to Slack
        if result and say:
            await _report_result(result, thread_id, say)

        # Update DB with final results
        if result and _db:
            await _update_fix_history_from_result(thread_id, result)

    except Exception as e:
        logger.error("graph_resume_failed", thread_id=thread_id, error=str(e))
        if say:
            await say(f":x: 작업 중 오류: {str(e)[:300]}")


async def _report_result(result: dict, thread_id: str, say) -> None:
    """Report graph execution result to Slack."""
    branch = result.get("git_branch")
    commit = result.get("git_commit_hash")
    modified = result.get("actually_modified_files", [])
    deployment = result.get("deployment")
    staging = result.get("staging_result")
    post_status = result.get("post_fix_status")

    # Code fix result
    if commit and modified:
        files_str = "\n".join(f"• `{f}`" for f in modified)

        # Push to GitHub
        github_url = await _push_branch_to_github(branch)
        github_msg = f"\n*GitHub:* {github_url}" if github_url else ""

        await say(
            f":white_check_mark: 코드 수정 완료\n"
            f"*브랜치:* `{branch}`\n*커밋:* `{commit[:8]}`\n"
            f"*수정 파일:*\n{files_str}{github_msg}"
        )
    elif branch and not commit:
        await say(f":warning: 코드 수정을 적용했지만 변경된 파일이 없습니다.\n브랜치: `{branch}`")
        return

    # Build result
    if deployment:
        await say(f":white_check_mark: 이미지 빌드 완료: `{deployment['harbor_image']}`")

        # Staging
        if staging == "healthy":
            await say(":white_check_mark: 스테이징 검증 통과")
        elif staging:
            await say(f":x: 스테이징 검증 실패: `{staging}`")
            return

        # Production
        if post_status == "deployed":
            from src.config.settings import get_settings
            from src.slack.bot import get_slack_app
            settings = get_settings()
            slack_app = get_slack_app()

            git_repo_url = settings.target_projects[0].git_repo.replace(".git", "") if settings.target_projects else ""
            branch_url = f"{git_repo_url}/tree/{branch}" if git_repo_url.startswith("http") and branch else ""

            blocks = [
                {"type": "section", "text": {"type": "mrkdwn", "text":
                    f":tada: *프로덕션 배포 완료*\n"
                    f"*이미지:* `{deployment['harbor_image']}`\n"
                    f"*브랜치:* `{branch}` ({commit[:8] if commit else ''})\n"
                    f"{f'*GitHub:* {branch_url}' if branch_url else ''}"
                }},
                {"type": "divider"},
                {"type": "section", "text": {"type": "mrkdwn", "text": "변경사항을 어떻게 처리할까요?"}},
                {"type": "actions", "block_id": f"git_{thread_id}", "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": "PR 생성"},
                     "style": "primary", "action_id": "create_pr", "value": f"{thread_id}|{branch}"},
                    {"type": "button", "text": {"type": "plain_text", "text": "바로 Merge"},
                     "action_id": "merge_branch", "value": f"{thread_id}|{branch}"},
                    {"type": "button", "text": {"type": "plain_text", "text": "브랜치만 유지"},
                     "action_id": "keep_branch", "value": f"{thread_id}|{branch}"},
                ]},
            ]
            await slack_app.client.chat_postMessage(
                channel=settings.slack.channel, blocks=blocks,
                text=f"배포 완료 - 브랜치 처리 방법을 선택하세요",
            )
        elif post_status == "rollback":
            await say(":warning: 프로덕션 배포 실패 → 자동 롤백됨")
        elif post_status:
            await say(f"배포 상태: {post_status}")
    elif not deployment and commit:
        await say(":warning: 이미지 빌드에 실패했습니다.")


async def _update_fix_history_from_result(thread_id: str, result: dict) -> None:
    """Update fix history DB with graph execution results."""
    from src.server.scheduler import _db
    if not _db:
        return

    try:
        history = await _db.list_fix_history(limit=20)
        for h in history:
            if h.get("thread_id") == thread_id:
                update = {}
                if result.get("git_branch"):
                    update["git_branch"] = result["git_branch"]
                if result.get("git_commit_hash"):
                    update["git_commit"] = result["git_commit_hash"]
                deployment = result.get("deployment")
                if deployment:
                    update["harbor_image"] = deployment.get("harbor_image")
                if result.get("staging_result"):
                    update["staging_result"] = result["staging_result"]
                update["production_deployed"] = result.get("post_fix_status") == "deployed"

                if update:
                    await _db.update_fix_history(str(h["id"]), **update)
                break
    except Exception as e:
        logger.error("db_update_results_failed", error=str(e))


async def _push_branch_to_github(branch: str) -> str | None:
    """Push branch to GitHub."""
    import subprocess
    from src.config.settings import get_settings

    settings = get_settings()
    token = settings.github.token
    user = settings.github.user
    repo_url = settings.target_projects[0].git_repo if settings.target_projects else ""
    project_root = settings.target_projects[0].root_path if settings.target_projects else ""

    if not token or not repo_url or not project_root:
        return None

    auth_url = repo_url.replace("https://", f"https://{user}:{token}@")

    subprocess.run(["git", "-C", project_root, "remote", "set-url", "origin", auth_url],
                   capture_output=True, text=True)
    result = subprocess.run(
        ["git", "-C", project_root, "push", "-u", "origin", branch, "--force"],
        capture_output=True, text=True, timeout=30,
    )

    if result.returncode != 0:
        logger.error("github_push_failed", stderr=result.stderr[:200])
        return None

    return repo_url.replace(".git", "") + f"/tree/{branch}"


async def _github_create_pr(branch: str) -> str | None:
    """Create a GitHub PR."""
    import httpx
    from src.config.settings import get_settings

    settings = get_settings()
    token = settings.github.token
    repo_url = settings.target_projects[0].git_repo if settings.target_projects else ""
    if not token or not repo_url:
        return None

    parts = repo_url.replace("https://github.com/", "").replace(".git", "").split("/")
    if len(parts) < 2:
        return None

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.github.com/repos/{parts[0]}/{parts[1]}/pulls",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"},
            json={
                "title": f"fix: Auto-fix by Error Log Agent ({branch})",
                "head": branch, "base": "main",
                "body": f"Error Log Agent 자동 수정 PR\n\n브랜치: `{branch}`",
            },
            timeout=15,
        )

    if resp.status_code == 201:
        return resp.json().get("html_url", "")
    return None


async def _github_merge_branch(branch: str) -> tuple[bool, str]:
    """Merge branch into main via GitHub API."""
    import httpx
    from src.config.settings import get_settings

    settings = get_settings()
    token = settings.github.token
    repo_url = settings.target_projects[0].git_repo if settings.target_projects else ""
    if not token or not repo_url:
        return False, "GitHub 설정 없음"

    parts = repo_url.replace("https://github.com/", "").replace(".git", "").split("/")
    if len(parts) < 2:
        return False, "잘못된 리포 URL"

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.github.com/repos/{parts[0]}/{parts[1]}/merges",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"},
            json={"base": "main", "head": branch,
                  "commit_message": f"Merge {branch} - Auto-fix by Error Log Agent"},
            timeout=15,
        )

    if resp.status_code in (201, 204):
        return True, "Merge 완료"
    elif resp.status_code == 409:
        compare_url = repo_url.replace(".git", "") + f"/compare/main...{branch}"
        return False, f"Merge conflict 발생. GitHub에서 직접 해결해주세요: {compare_url}"
    return False, f"Merge 실패 (HTTP {resp.status_code})"
