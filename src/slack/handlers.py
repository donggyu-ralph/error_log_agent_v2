"""Slack interactive message handlers."""
import json
from slack_bolt.async_app import AsyncApp

from src.config.logging_config import get_logger

logger = get_logger(__name__)

# Thread ID → approval config (in-memory cache, persisted to DB as backup)
_pending_approvals: dict[str, dict] = {}


def register_pending_approval(thread_id: str, graph_config: dict) -> None:
    _pending_approvals[thread_id] = graph_config


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

        await _handle_approval(thread_id, {"action": "approve", "user": user}, say)

    @app.action("reject_fix")
    async def handle_reject(ack, body, say, client):
        await ack()
        thread_id = body["actions"][0]["value"]
        user = body["user"]["username"]

        logger.info("fix_rejected", thread_id=thread_id, user=user)
        await _disable_buttons(client, body, f":x: *거절됨* by @{user}")

        # Update DB
        try:
            from src.server.scheduler import _db
            if _db:
                history = await _db.list_fix_history(limit=20)
                for h in history:
                    if h.get("thread_id") == thread_id:
                        await _db.update_fix_history(str(h["id"]), action="reject")
                        break
        except Exception as e:
            logger.error("db_reject_update_failed", error=str(e))

        await say(f"수정이 취소되었습니다.")

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
                        "placeholder": {"type": "plain_text", "text": "예: retry 로직을 exponential backoff로 변경해주세요"},
                    },
                }],
            },
        )

    @app.view("")
    async def handle_feedback_submit(ack, body, view):
        await ack()
        callback_id = view["callback_id"]
        if not callback_id.startswith("feedback_modal_"):
            return
        thread_id = callback_id.replace("feedback_modal_", "")
        user = body["user"]["username"]
        feedback_text = view["state"]["values"]["feedback_input"]["feedback_text"]["value"]
        logger.info("feedback_received", thread_id=thread_id, feedback=feedback_text[:100])
        # TODO: re-analyze with feedback

    @app.action("rollback_deploy")
    async def handle_rollback(ack, body, say, client):
        await ack()
        thread_id = body["actions"][0]["value"]
        user = body["user"]["username"]
        await _disable_buttons(client, body, f":warning: *롤백 요청됨* by @{user}")

        from src.deployer.rollback import rollback_deployment
        config = _pending_approvals.get(thread_id, {})
        deployment = config.get("deployment", {})
        if deployment:
            success = await rollback_deployment(
                deployment["production_namespace"],
                deployment["production_deployment"],
                deployment.get("previous_image"),
            )
            await say("롤백 완료." if success else "롤백 실패. 수동 확인 필요.")

    @app.action("create_pr")
    async def handle_create_pr(ack, body, say, client):
        await ack()
        value = body["actions"][0]["value"]
        thread_id, branch = value.split("|", 1)
        user = body["user"]["username"]

        await _disable_buttons(client, body, f":pull_request: *PR 생성 요청됨* by @{user}")

        result = await _github_create_pr(branch)
        if result:
            await say(f":white_check_mark: PR이 생성되었습니다: {result}")
        else:
            await say(":warning: PR 생성에 실패했습니다. GitHub에서 직접 생성해주세요.")

    @app.action("merge_branch")
    async def handle_merge(ack, body, say, client):
        await ack()
        value = body["actions"][0]["value"]
        thread_id, branch = value.split("|", 1)
        user = body["user"]["username"]

        await _disable_buttons(client, body, f":merge: *Merge 요청됨* by @{user}")

        success = await _github_merge_branch(branch)
        if success:
            await say(f":white_check_mark: `{branch}`가 `main`에 merge되었습니다.")
        else:
            await say(":warning: Merge에 실패했습니다. GitHub에서 직접 merge해주세요.")

    @app.action("keep_branch")
    async def handle_keep_branch(ack, body, say, client):
        await ack()
        value = body["actions"][0]["value"]
        thread_id, branch = value.split("|", 1)
        user = body["user"]["username"]

        await _disable_buttons(client, body, f":bookmark: *브랜치 유지* by @{user}")
        await say(f"브랜치 `{branch}`를 유지합니다. 나중에 수동으로 처리해주세요.")

    @app.event("app_mention")
    async def handle_mention(event, say):
        text = event.get("text", "").lower()
        if "상태" in text or "status" in text:
            await say("현재 에이전트 상태: 실행 중")
        elif "통계" in text or "stats" in text:
            await say("대시보드: https://agent.atdev.ai")
        else:
            await say("사용 가능한 명령: `상태`, `통계`")


async def _handle_approval(thread_id: str, feedback: dict, say=None) -> None:
    """Handle approval: run code fix → build → deploy pipeline."""
    logger.info("handling_approval", thread_id=thread_id)

    try:
        from src.server.scheduler import _db
        from src.agent.graph import get_agent

        # Find fix history from DB
        fix_history_id = None
        fix_plan = None
        error_logs = []
        analysis = ""

        if _db:
            history = await _db.list_fix_history(limit=20)
            for h in history:
                if h.get("thread_id") == thread_id:
                    fix_history_id = str(h["id"])
                    fix_plan = h.get("fix_plan")
                    analysis = h.get("analysis", "")
                    await _db.update_fix_history(fix_history_id, action="approve")
                    break

            # Get error logs for this thread
            errors = await _db.list_error_logs(limit=10)
            error_logs = errors[:1] if errors else []

        if not fix_plan:
            logger.warning("no_fix_plan_found", thread_id=thread_id)
            if say:
                await say(f":warning: 수정 계획을 찾을 수 없습니다. (thread: {thread_id[:8]})")
            return

        # Run the fix pipeline directly (skip collect/analyze/plan/approval)
        agent = get_agent()
        state = {
            "thread_id": thread_id,
            "error_logs": error_logs,
            "source_code_context": {},
            "analysis": analysis,
            "fix_plan": fix_plan if isinstance(fix_plan, dict) else {},
            "human_feedback": feedback,
            "git_branch": None,
            "git_commit_hash": None,
            "deployment": None,
            "staging_result": None,
            "post_fix_status": None,
            "iteration_count": 0,
            "max_iterations": 3,
            "messages": [],
            "actually_modified_files": [],
        }

        # Run fix nodes directly instead of full graph
        from src.agent.nodes.code_fixer import apply_fix_node
        from src.agent.nodes.image_builder import build_image_node
        from src.agent.nodes.k8s_deployer import deploy_staging_node, verify_staging_node, deploy_production_node

        if say:
            await say(":hammer: 코드 수정 중...")

        # Step 1: Apply fix
        fix_result = await apply_fix_node(state)
        state.update(fix_result)

        modified = fix_result.get("actually_modified_files", [])
        commit = fix_result.get("git_commit_hash")
        branch = fix_result.get("git_branch")

        if not commit:
            if say:
                await say(f":warning: 코드 수정을 적용했지만 변경된 파일이 없습니다.\n브랜치: `{branch}`")
            if fix_history_id and _db:
                await _db.update_fix_history(fix_history_id, git_branch=branch)
            return

        # Push branch to GitHub
        github_url = None
        try:
            github_url = await _push_branch_to_github(project_root=state["fix_plan"].get("_project_root", "/workspace/data-pipeline-service"), branch=branch)
        except Exception as e:
            logger.warning("github_push_failed", error=str(e))

        if say:
            files_str = "\n".join(f"• `{f}`" for f in modified)
            msg = f":white_check_mark: 코드 수정 완료\n*브랜치:* `{branch}`\n*커밋:* `{commit[:8]}`\n*수정 파일:*\n{files_str}"
            if github_url:
                msg += f"\n*GitHub:* {github_url}"
            await say(msg)

        # Step 2: Build image
        if say:
            await say(":package: Docker 이미지 빌드 중...")

        build_result = await build_image_node(state)
        state.update(build_result)

        deployment = build_result.get("deployment")
        if not deployment:
            if say:
                await say(":warning: 이미지 빌드에 실패했습니다.")
            if fix_history_id and _db:
                await _db.update_fix_history(fix_history_id, git_branch=branch, git_commit=commit)
            return

        if say:
            await say(f":white_check_mark: 이미지 빌드 완료: `{deployment['harbor_image']}`")

        # Step 3: Deploy staging
        if say:
            await say(":rocket: 스테이징 배포 중...")

        staging_result = await deploy_staging_node(state)
        state.update(staging_result)

        # Step 4: Verify staging
        verify_result = await verify_staging_node(state)
        state.update(verify_result)

        staging_status = verify_result.get("staging_result", "unhealthy")

        if staging_status != "healthy":
            if say:
                await say(f":x: 스테이징 검증 실패 (`{staging_status}`). 프로덕션 배포를 중단합니다.")
            if fix_history_id and _db:
                await _db.update_fix_history(
                    fix_history_id, git_branch=branch, git_commit=commit,
                    harbor_image=deployment["harbor_image"], staging_result=staging_status,
                )
            return

        if say:
            await say(":white_check_mark: 스테이징 검증 통과! 프로덕션 배포 중...")

        # Step 5: Deploy production
        prod_result = await deploy_production_node(state)
        state.update(prod_result)

        post_status = prod_result.get("post_fix_status", "unknown")

        # Update DB
        if fix_history_id and _db:
            await _db.update_fix_history(
                fix_history_id, git_branch=branch, git_commit=commit,
                harbor_image=deployment["harbor_image"],
                staging_result=staging_status,
                production_deployed=(post_status == "deployed"),
            )

        if say:
            if post_status == "deployed":
                from src.slack.bot import get_slack_app
                from src.config.settings import get_settings
                slack_app = get_slack_app()
                settings = get_settings()

                # Send deployment complete with Git action buttons
                git_repo_url = settings.target_projects[0].git_repo.replace(".git", "") if settings.target_projects else ""
                branch_url = f"{git_repo_url}/tree/{branch}" if git_repo_url.startswith("http") else ""

                blocks = [
                    {"type": "section", "text": {"type": "mrkdwn", "text":
                        f":tada: *배포 완료*\n"
                        f"*이미지:* `{deployment['harbor_image']}`\n"
                        f"*브랜치:* `{branch}` ({commit[:8]})\n"
                        f"{f'*GitHub:* {branch_url}' if branch_url else ''}"
                    }},
                    {"type": "divider"},
                    {"type": "section", "text": {"type": "mrkdwn", "text":
                        "변경사항을 어떻게 처리할까요?"
                    }},
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
                    text=f"배포 완료 - 브랜치 {branch} 처리 방법을 선택하세요",
                )
            elif post_status == "rollback":
                await say(":warning: 프로덕션 배포 실패 → 자동 롤백됨")
            else:
                await say(f"배포 상태: {post_status}")

        logger.info("approval_pipeline_completed", thread_id=thread_id, status=post_status)

    except Exception as e:
        logger.error("approval_handling_failed", thread_id=thread_id, error=str(e))
        if say:
            await say(f":x: 수정 작업 중 오류: {str(e)[:300]}")


async def _push_branch_to_github(project_root: str, branch: str) -> str | None:
    """Push a branch to GitHub remote. Returns the branch URL."""
    import subprocess
    from src.config.settings import get_settings

    settings = get_settings()
    token = settings.github.token
    user = settings.github.user
    repo_url = settings.target_projects[0].git_repo if settings.target_projects else ""

    if not token or not repo_url:
        logger.warning("github_not_configured")
        return None

    # Set remote URL with token
    auth_url = repo_url.replace("https://", f"https://{user}:{token}@")

    result = subprocess.run(
        ["git", "-C", project_root, "remote", "get-url", "origin"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        subprocess.run(
            ["git", "-C", project_root, "remote", "add", "origin", auth_url],
            capture_output=True, text=True,
        )
    else:
        subprocess.run(
            ["git", "-C", project_root, "remote", "set-url", "origin", auth_url],
            capture_output=True, text=True,
        )

    push_result = subprocess.run(
        ["git", "-C", project_root, "push", "-u", "origin", branch, "--force"],
        capture_output=True, text=True, timeout=30,
    )

    if push_result.returncode != 0:
        logger.error("github_push_failed", stderr=push_result.stderr[:300])
        return None

    branch_url = repo_url.replace(".git", "") + f"/tree/{branch}"
    logger.info("github_branch_pushed", branch=branch, url=branch_url)
    return branch_url


async def _github_create_pr(branch: str) -> str | None:
    """Create a GitHub PR from the branch to main."""
    import httpx
    from src.config.settings import get_settings

    settings = get_settings()
    token = settings.github.token
    repo_url = settings.target_projects[0].git_repo if settings.target_projects else ""

    if not token or not repo_url:
        return None

    # Extract owner/repo from URL
    parts = repo_url.replace("https://github.com/", "").replace(".git", "").split("/")
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.github.com/repos/{owner}/{repo}/pulls",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
            },
            json={
                "title": f"fix: Auto-fix by Error Log Agent ({branch})",
                "head": branch,
                "base": "main",
                "body": f"Error Log Agent가 자동으로 생성한 수정 PR입니다.\n\n브랜치: `{branch}`",
            },
            timeout=15,
        )

    if resp.status_code == 201:
        pr_url = resp.json().get("html_url", "")
        logger.info("github_pr_created", url=pr_url)
        return pr_url
    else:
        logger.error("github_pr_failed", status=resp.status_code, body=resp.text[:300])
        return None


async def _github_merge_branch(branch: str) -> bool:
    """Merge a branch into main via GitHub API."""
    import httpx
    from src.config.settings import get_settings

    settings = get_settings()
    token = settings.github.token
    repo_url = settings.target_projects[0].git_repo if settings.target_projects else ""

    if not token or not repo_url:
        return False

    parts = repo_url.replace("https://github.com/", "").replace(".git", "").split("/")
    if len(parts) < 2:
        return False
    owner, repo = parts[0], parts[1]

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.github.com/repos/{owner}/{repo}/merges",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
            },
            json={
                "base": "main",
                "head": branch,
                "commit_message": f"Merge {branch} - Auto-fix by Error Log Agent",
            },
            timeout=15,
        )

    if resp.status_code in (201, 204):
        logger.info("github_merge_completed", branch=branch)
        return True
    else:
        logger.error("github_merge_failed", status=resp.status_code, body=resp.text[:300])
        return False
