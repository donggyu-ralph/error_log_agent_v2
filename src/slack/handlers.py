"""Slack interactive message handlers."""
from slack_bolt.async_app import AsyncApp

from src.config.logging_config import get_logger

logger = get_logger(__name__)

# Thread ID → graph resume callback
_pending_approvals: dict[str, dict] = {}


def register_pending_approval(thread_id: str, graph_config: dict) -> None:
    """Register a pending approval for a thread."""
    _pending_approvals[thread_id] = graph_config


def register_handlers(app: AsyncApp) -> None:
    """Register all Slack interactive message handlers."""

    @app.action("approve_fix")
    async def handle_approve(ack, body, say):
        await ack()
        thread_id = body["actions"][0]["value"]
        user = body["user"]["username"]

        logger.info("fix_approved", thread_id=thread_id, user=user)
        await say(f"*승인됨* by @{user}. 코드 수정을 시작합니다.")

        # Resume the LangGraph agent
        await _resume_graph(thread_id, {"action": "approve", "user": user})

    @app.action("reject_fix")
    async def handle_reject(ack, body, say):
        await ack()
        thread_id = body["actions"][0]["value"]
        user = body["user"]["username"]

        logger.info("fix_rejected", thread_id=thread_id, user=user)
        await say(f"*거절됨* by @{user}. 수정을 취소합니다.")

        await _resume_graph(thread_id, {"action": "reject", "user": user})

    @app.action("feedback_fix")
    async def handle_feedback(ack, body, client):
        await ack()
        thread_id = body["actions"][0]["value"]

        # Open a modal for feedback input
        await client.views_open(
            trigger_id=body["trigger_id"],
            view={
                "type": "modal",
                "callback_id": f"feedback_modal_{thread_id}",
                "title": {"type": "plain_text", "text": "피드백 입력"},
                "submit": {"type": "plain_text", "text": "전송"},
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "feedback_input",
                        "label": {"type": "plain_text", "text": "수정 방향에 대한 피드백을 입력하세요"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "feedback_text",
                            "multiline": True,
                            "placeholder": {"type": "plain_text", "text": "예: retry 로직을 exponential backoff로 변경해주세요"},
                        },
                    }
                ],
            },
        )

    @app.view_regex(r"feedback_modal_.*")
    async def handle_feedback_submit(ack, body, view):
        await ack()
        callback_id = view["callback_id"]
        thread_id = callback_id.replace("feedback_modal_", "")
        user = body["user"]["username"]
        feedback_text = view["state"]["values"]["feedback_input"]["feedback_text"]["value"]

        logger.info("feedback_received", thread_id=thread_id, user=user, feedback=feedback_text[:100])

        await _resume_graph(thread_id, {
            "action": "feedback",
            "user": user,
            "message": feedback_text,
        })

    @app.action("rollback_deploy")
    async def handle_rollback(ack, body, say):
        await ack()
        thread_id = body["actions"][0]["value"]
        user = body["user"]["username"]

        logger.info("rollback_requested", thread_id=thread_id, user=user)
        await say(f"*롤백 요청됨* by @{user}. 이전 버전으로 롤백합니다.")

        # Trigger rollback
        from src.deployer.rollback import rollback_deployment
        config = _pending_approvals.get(thread_id, {})
        deployment = config.get("deployment", {})
        if deployment:
            success = await rollback_deployment(
                deployment["production_namespace"],
                deployment["production_deployment"],
                deployment.get("previous_image"),
            )
            if success:
                await say("롤백이 완료되었습니다.")
            else:
                await say("롤백에 실패했습니다. 수동 확인이 필요합니다.")

    @app.event("app_mention")
    async def handle_mention(event, say):
        """Handle @mention commands."""
        text = event.get("text", "").lower()

        if "상태" in text or "status" in text:
            await say("현재 에이전트 상태: 실행 중")
        elif "통계" in text or "stats" in text:
            await say("웹 대시보드에서 상세 통계를 확인하세요.")
        else:
            await say("사용 가능한 명령: `상태`, `통계`")


async def _resume_graph(thread_id: str, feedback: dict) -> None:
    """Resume the LangGraph agent with human feedback."""
    config = _pending_approvals.pop(thread_id, None)
    if not config:
        logger.warning("no_pending_approval", thread_id=thread_id)
        return

    from langgraph.types import Command
    graph = config.get("graph")
    graph_config = config.get("config")

    if graph and graph_config:
        await graph.ainvoke(
            Command(resume=feedback),
            config=graph_config,
        )
