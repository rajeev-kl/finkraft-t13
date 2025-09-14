import json

import streamlit as st

from ai.integrations import generate_reply_draft, get_intent
from core.logger import get_recent_logs, setup_logger
from core.orchestrator import process_email_threads
from core.rules import rule_based_intent_and_action
from db.crud import (
    create_ai_suggestion,
    create_email_draft,
    get_latest_suggestion_for_message,
    has_accepted_decision_for_suggestion,
    has_sent_draft_for_message,
    list_draft,
    list_messages_for_thread,
    list_sent,
    list_threads,
    mark_draft_sent,
    record_user_decision,
)
from db.session import SessionLocal, ensure_db_schema

# Set up logging
logger = setup_logger()


def render_thread(thread_summary):
    st.json(thread_summary)


def main():
    # Use wide layout so the main component expands across the page
    try:
        st.set_page_config(layout="wide")
    except Exception:
        # set_page_config may only be called once; ignore if already set
        pass
    st.title("Email Behavior Orchestrator")

    st.sidebar.header("Settings")
    st.sidebar.write("Configure your preferences here.")
    # Sidebar quick links for Drafts / Sent
    st.sidebar.markdown("---")
    view_choice = st.sidebar.radio("Navigate", options=["Threads", "Drafts", "Sent"], index=0)

    # Use a stable session_state key for the uploader so we can clear it after processing
    uploader_key = "uploaded_threads_file"
    uploaded_file = st.sidebar.file_uploader("Upload email threads (JSON)", type=["json"], key=uploader_key)

    # Only process the uploaded file when the user explicitly clicks the button.
    if uploaded_file is not None:
        filename = getattr(uploaded_file, "name", "uploaded_file")
        st.sidebar.write(f"Selected file: {filename}")
        if st.sidebar.button("Process uploaded file", key=f"process-{filename}"):
            email_threads = process_email_threads(uploaded_file)
            if email_threads:
                st.success(f"Processed {len(email_threads)} threads")
            else:
                st.warning("No email threads found or processed.")

            # Clear the uploader from session_state so the file is not reprocessed on reruns
            try:
                del st.session_state[uploader_key]
            except Exception:
                # If clearing fails, just continue; this is non-fatal
                logger.warning("Failed to clear uploader session_state key")

    # Show persisted threads from DB
    # Ensure DB schema / lightweight migrations run before opening sessions
    try:
        ensure_db_schema()
    except Exception:
        # non-fatal; continue and let SQLAlchemy surface errors
        pass
    db = SessionLocal()
    try:
        threads = list_threads(db, limit=50)
        # If user selected Drafts or Sent, display that view and return early
        if view_choice == "Drafts":
            st.subheader("All Drafts")
            drafts = list_draft(db)
            if not drafts:
                st.info("No drafts created yet.")
            for d in drafts:
                with st.expander(f"Draft {d.id} — thread {d.thread_id} (status={d.status})"):
                    # Show thread summary
                    thr = None
                    try:
                        from db.crud import get_thread

                        thr = get_thread(db, d.thread_id)
                    except Exception:
                        thr = None
                    if thr:
                        st.markdown(f"**Thread {thr.id} — {thr.subject}**")
                        st.write(f"Sender: {thr.sender} Recipient: {thr.recipient}")
                    # Show any suggestions related to this draft
                    try:
                        from db.crud import list_suggestions_for_message

                        if d.message_id:
                            sugs = list_suggestions_for_message(db, d.message_id)
                            if sugs:
                                for sug in sugs:
                                    st.write(
                                        (
                                            f"AI Suggestion: intent={sug.intent} "
                                            f"confidence={sug.confidence:.2f} "
                                            f"action={sug.suggested_action}"
                                        )
                                    )
                                    # show raw AI response for provenance/debugging
                                    raw = getattr(sug, "raw_response", None)
                                    if raw:
                                        try:
                                            parsed = json.loads(raw)
                                            with st.expander(f"Raw AI response (JSON) - suggestion {sug.id}"):
                                                st.json(parsed)
                                        except Exception:
                                            with st.expander(f"Raw AI response - suggestion {sug.id}"):
                                                st.text(raw)
                                        st.write(
                                            f"{sug.id}: intent={sug.intent}\n"
                                            f"action={sug.suggested_action}\n"
                                            f"confidence={sug.confidence:.2f}"
                                        )
                    except Exception:
                        pass

                    st.write(d.body)
                    if d.customer_provided:
                        try:
                            st.write("Customer-provided:")
                            st.json(json.loads(d.customer_provided))
                        except Exception:
                            st.write(d.customer_provided)
                    if d.responder_provided:
                        try:
                            st.write("Responder-provided:")
                            st.json(json.loads(d.responder_provided))
                        except Exception:
                            st.write(d.responder_provided)

                    col_send, col_del = st.columns([1, 1])
                    with col_send:
                        if st.button(f"Send draft {d.id}", key=f"send-draft-side-{d.id}"):
                            try:
                                mark_draft_sent(db=db, draft_id=d.id)
                                st.success("Draft marked as sent")
                                st.experimental_rerun()
                            except Exception as e:
                                st.error(f"Failed to mark draft sent: {e}")
                    with col_del:
                        if st.button(f"Delete draft {d.id}", key=f"delete-draft-side-{d.id}"):
                            try:
                                from db.crud import delete_email_draft

                                delete_email_draft(db, d.id)
                                st.success("Draft deleted")
                                st.experimental_rerun()
                            except Exception as e:
                                st.error(f"Failed to delete draft: {e}")
            return
        if view_choice == "Sent":
            st.subheader("Sent Drafts")
            sent = list_sent(db)
            if not sent:
                st.info("No sent drafts yet.")
            for d in sent:
                with st.expander(f"Sent Draft {d.id} — thread {d.thread_id} (sent at {d.sent_at})"):
                    st.write(f"Thread: {d.thread_id}  Message: {d.message_id}  Suggestion: {d.suggestion_id}")
                    st.write(d.body)
            return
        st.subheader("Persisted Threads")
        if not threads:
            st.info("No threads persisted yet. Upload a sample JSON on the left to start.")
        for t in threads:
            with st.expander(f"{t.id}: {t.subject}"):
                st.write(f"Sender: {t.sender}  Recipient: {t.recipient}  Status: {t.status}")
                msgs = list_messages_for_thread(db, t.id)
                if not msgs:
                    st.write("No messages recorded for this thread.")
                for m in msgs:
                    st.markdown(f"**Message {m.id}** — from {m.sender} to {m.recipient}")
                    st.write(m.body)
                    sug = get_latest_suggestion_for_message(db, m.id)
                    if sug:
                        st.write(
                            (
                                f"AI Suggestion: intent={sug.intent} "
                                f"confidence={sug.confidence:.2f} "
                                f"action={sug.suggested_action}"
                            )
                        )
                        # Try to parse required_fields (stored as JSON string) and follow_up_question
                        req_fields = None
                        try:
                            raw_rf = getattr(sug, "required_fields", None)
                            if raw_rf:
                                req_fields = json.loads(raw_rf)
                                if not isinstance(req_fields, list):
                                    # keep legacy list as None here; we'll handle structured shapes separately
                                    req_fields = None
                        except Exception:
                            req_fields = None

                        # Also compute structured required fields (customer/responder) early so Accept button can decide
                        req_customer = None
                        req_responder = None
                        try:
                            raw = getattr(sug, "required_fields", None)
                            if raw:
                                try:
                                    parsed = json.loads(raw)
                                    if isinstance(parsed, dict):
                                        req_customer = parsed.get("customer")
                                        req_responder = parsed.get("responder")
                                    elif isinstance(parsed, list):
                                        req_customer = [{"name": x, "hint": None, "required": True} for x in parsed]
                                except Exception:
                                    req_customer = None
                            # try attributes too
                            if not req_customer:
                                rc = getattr(sug, "required_fields_customer", None)
                                rr = getattr(sug, "required_fields_responder", None)
                                req_customer = rc
                                req_responder = rr
                        except Exception:
                            req_customer = None
                            req_responder = None

                        follow_up = getattr(sug, "follow_up_question", None)
                        if follow_up:
                            st.info(f"Follow-up question: {follow_up}")

                        if req_fields:
                            st.warning(
                                f"Required information needed before generating a draft: {', '.join(req_fields)}"
                            )
                        # Determine acceptance/sent state for UI disabling
                        accepted_state = st.session_state.get(f"accepted_suggestion_{sug.id}") if sug else False
                        try:
                            if sug and not accepted_state:
                                accepted_state = has_accepted_decision_for_suggestion(db=db, suggestion_id=sug.id)
                        except Exception:
                            accepted_state = accepted_state

                        # prefer session_state flag for immediate UI feedback when a draft was just sent
                        sent_state = st.session_state.get(f"sent_for_message_{m.id}", False)
                        try:
                            if sug and not sent_state:
                                sent_state = has_sent_draft_for_message(db=db, message_id=m.id)
                        except Exception:
                            sent_state = sent_state

                        # Arrange action controls in a single horizontal row (4 equal columns)
                        btn_cols = st.columns([1, 1, 1, 1])
                        # Column 0: Accept / Accepted badge
                        with btn_cols[0]:
                            if accepted_state:
                                st.markdown(
                                    '<div style="background:#d4f8e8;'
                                    "padding:6px;border-radius:4px;"
                                    'text-align:center;color:#044d2c">Accepted</div>',
                                    unsafe_allow_html=True,
                                )
                            else:
                                if st.button(f"Accept#{sug.id}", key=f"accept-{sug.id}"):
                                    if (req_customer or req_responder) and not st.session_state.get(
                                        f"provided_required_{sug.id}", False
                                    ):
                                        st.session_state[f"show_required_form_{sug.id}"] = True
                                    else:
                                        record_user_decision(
                                            db=db, suggestion_id=sug.id, user="demo_user", decision="accept"
                                        )
                                        st.session_state[f"accepted_suggestion_{sug.id}"] = True
                                        st.success("Accepted suggestion")
                                        if not (req_customer or req_responder):
                                            try:
                                                suggestion_text = sug.suggested_action or sug.intent
                                                draft_body = generate_reply_draft(
                                                    suggestion=suggestion_text, original_message=m.body
                                                )
                                                if draft_body:
                                                    d = create_email_draft(
                                                        db=db,
                                                        thread_id=t.id,
                                                        body=draft_body,
                                                        message_id=m.id,
                                                        suggestion_id=sug.id,
                                                        customer_provided={},
                                                        responder_provided={},
                                                        status="draft",
                                                    )
                                                    st.session_state[f"draft_for_message_{m.id}"] = d.body
                                                    st.session_state[f"cust_values_{sug.id}"] = {}
                                                    st.session_state[f"resp_values_{sug.id}"] = {}
                                                    st.info("Auto-generated draft created from accepted suggestion")
                                            except Exception as e:
                                                logger.error(f"Failed to auto-generate draft on accept: {e}")
                        # Column 1: Respond
                        with btn_cols[1]:
                            if sent_state:
                                st.markdown(
                                    (
                                        '<div style="background:#d4f8e8;padding:6px;'
                                        "border-radius:4px;text-align:center;"
                                        'color:#044d2c">Sent</div>'
                                    ),
                                    unsafe_allow_html=True,
                                )
                            else:
                                # Check DB for an existing unsent draft for this message
                                try:
                                    from db.crud import get_latest_draft_for_message

                                    latest_draft = get_latest_draft_for_message(db=db, message_id=m.id)
                                except Exception:
                                    latest_draft = None

                                if not accepted_state:
                                    if sug and st.button(f"Respond to message {m.id}", key=f"respond-{m.id}"):
                                        draft_text = generate_reply_draft(
                                            suggestion=sug.suggested_action or sug.intent, original_message=m.body
                                        )
                                        st.session_state[f"draft_for_message_{m.id}"] = draft_text
                                else:
                                    if latest_draft or st.session_state.get(f"draft_for_message_{m.id}"):
                                        # load DB draft to session_state when Edit clicked
                                        if st.button(f"Edit draft {m.id}", key=f"edit-draft-{m.id}"):
                                            if latest_draft and not st.session_state.get(f"draft_for_message_{m.id}"):
                                                st.session_state[f"draft_for_message_{m.id}"] = latest_draft.body
                                            # otherwise, leave existing session_state draft as-is to open editor
                        # Column 2: Override input
                        with btn_cols[2]:
                            override = st.text_input(
                                f"Override action for suggestion {sug.id}", key=f"override-{sug.id}"
                            )
                        # Column 3: Override button + Re-evaluate
                        with btn_cols[3]:
                            if st.button(f"Override#{sug.id}", key=f"override-btn-{sug.id}"):
                                if override:
                                    record_user_decision(
                                        db=db, suggestion_id=sug.id, user="demo_user", decision=f"override:{override}"
                                    )
                                    st.success("Override recorded")
                                else:
                                    st.warning("Enter override text before submitting")
                            if st.button(f"Re-evaluate thread {t.id}", key=f"reeval-msg-{m.id}"):
                                for mm in msgs:
                                    latest = get_latest_suggestion_for_message(db, mm.id)
                                    should_create = False
                                    try:
                                        ai_resp = get_intent([{"role": "user", "content": mm.body}])
                                        intent = getattr(ai_resp, "intent", "unknown")
                                        confidence = getattr(ai_resp, "confidence", 0.0)
                                    except Exception:
                                        intent = "unknown"
                                        confidence = 0.0
                                    suggested_action = "no-action"
                                    if intent == "unknown" or confidence <= 0.0:
                                        r_intent, r_conf, r_action = rule_based_intent_and_action(mm.body)
                                        intent = r_intent
                                        confidence = r_conf
                                        suggested_action = r_action
                                    else:
                                        if intent == "interested":
                                            suggested_action = "send_pricing"
                                        elif intent == "not_interested":
                                            suggested_action = "close_thread"
                                    if latest is None:
                                        should_create = True
                                    else:
                                        try:
                                            if confidence > (latest.confidence or 0.0):
                                                should_create = True
                                        except Exception:
                                            should_create = True
                                    if should_create and confidence > 0.0:
                                        try:
                                            required_fields = getattr(ai_resp, "required_fields", None)
                                            follow_up_question = getattr(ai_resp, "follow_up_question", None)
                                        except Exception:
                                            required_fields = None
                                            follow_up_question = None
                                        create_ai_suggestion(
                                            db=db,
                                            message_id=mm.id,
                                            intent=intent,
                                            confidence=confidence,
                                            suggested_action=suggested_action,
                                            required_fields=required_fields,
                                            follow_up_question=follow_up_question,
                                        )
                                st.success("Re-evaluated suggestions for this thread — refresh to see updates")

                        req_customer = None
                        req_responder = None
                        try:
                            raw = getattr(sug, "required_fields", None)
                            if raw:
                                # legacy: could be JSON string of an object {customer: [...], responder: [...]}
                                try:
                                    parsed = json.loads(raw)
                                    if isinstance(parsed, dict):
                                        req_customer = parsed.get("customer")
                                        req_responder = parsed.get("responder")
                                    elif isinstance(parsed, list):
                                        # legacy list of strings -> customer
                                        req_customer = [{"name": x, "hint": None, "required": True} for x in parsed]
                                except Exception:
                                    req_customer = None
                            # Also check newer dedicated attributes on suggestion (if available)
                            if not req_customer:
                                # attempt to read recently stored structured fields
                                try:
                                    rc = getattr(sug, "required_fields_customer", None)
                                    rr = getattr(sug, "required_fields_responder", None)
                                    req_customer = rc
                                    req_responder = rr
                                except Exception:
                                    pass
                        except Exception:
                            req_customer = None
                            req_responder = None

                        if req_customer or req_responder:
                            expanded = st.session_state.get(f"show_required_form_{sug.id}", False)
                            with st.expander("Provide required information to complete the action", expanded=expanded):
                                # Customer-facing inputs
                                st.markdown("**Customer-facing information**")
                                customer_inputs = {}
                                for spec in req_customer or []:
                                    # spec may be a dict {name,hint,required} or a string
                                    if isinstance(spec, str):
                                        name = spec
                                        hint = None
                                    else:
                                        name = spec.get("name")
                                        hint = spec.get("hint") if isinstance(spec, dict) else None
                                    key = f"cust_{sug.id}_{name}"
                                    label = f"{name}"
                                    if hint:
                                        label = f"{label} ({hint})"
                                    customer_inputs[name] = st.text_input(label, key=key)

                                st.markdown("---")
                                # Responder/internal inputs (render any suggested by AI, plus default small set)
                                st.markdown("**Responder / internal notes (optional)**")
                                responder_inputs = {}
                                # render AI-specified responder fields if present
                                if req_responder:
                                    for spec in req_responder:
                                        if isinstance(spec, str):
                                            rname = spec
                                            rhint = None
                                        else:
                                            rname = spec.get("name")
                                            rhint = spec.get("hint") if isinstance(spec, dict) else None
                                        rkey = f"resp_{sug.id}_{rname}"
                                        rlabel = f"{rname}"
                                        if rhint:
                                            rlabel = f"{rlabel} ({rhint})"
                                        responder_inputs[rname] = st.text_input(rlabel, key=rkey)
                                # plus a small default set
                                responder_fields = ["agent_notes", "follow_up_deadline", "billing_contact"]
                                for rf in responder_fields:
                                    rkey = f"resp_{sug.id}_{rf}"
                                    if rf not in responder_inputs:
                                        responder_inputs[rf] = st.text_input(f"{rf}", key=rkey)

                                if st.button(
                                    f"Confirm accept and generate draft #{sug.id}", key=f"confirm-accept-{sug.id}"
                                ):
                                    # Validate inputs: ensure customer-facing required fields are non-empty
                                    missing = [f for f, v in customer_inputs.items() if not v or str(v).strip() == ""]
                                    if missing:
                                        st.warning(f"Please provide values for: {', '.join(missing)}")
                                    else:
                                        # record acceptance
                                        record_user_decision(
                                            db=db, suggestion_id=sug.id, user="demo_user", decision="accept"
                                        )
                                        st.session_state[f"accepted_suggestion_{sug.id}"] = True
                                        # mark provided flag so form doesn't reappear
                                        st.session_state[f"provided_required_{sug.id}"] = True
                                        # hide the form
                                        st.session_state[f"show_required_form_{sug.id}"] = False

                                        provided_text = "\n".join([f"{k}: {v}" for k, v in customer_inputs.items()])
                                        augmented_message = m.body + "\n\nProvided information:\n" + provided_text

                                        try:
                                            suggestion_text = sug.suggested_action or sug.intent
                                            draft_body = generate_reply_draft(
                                                suggestion=suggestion_text, original_message=augmented_message
                                            )
                                            if draft_body:
                                                d = create_email_draft(
                                                    db=db,
                                                    thread_id=t.id,
                                                    body=draft_body,
                                                    message_id=m.id,
                                                    suggestion_id=sug.id,
                                                    customer_provided=customer_inputs,
                                                    responder_provided=responder_inputs,
                                                    status="draft",
                                                )
                                                st.session_state[f"cust_values_{sug.id}"] = customer_inputs
                                                st.session_state[f"resp_values_{sug.id}"] = responder_inputs
                                                st.session_state[f"draft_for_message_{m.id}"] = d.body
                                                st.info("Auto-generated draft created from accepted suggestion")
                                        except Exception as e:
                                            logger.error(
                                                f"Failed to auto-generate draft on accept with required fields: {e}"
                                            )
                        # Respond action is handled in the inline action row above

                        if f"draft_for_message_{m.id}" in st.session_state:
                            with st.expander(f"Draft reply for message {m.id}"):
                                draft_val = st.text_area(
                                    "Edit draft",
                                    value=st.session_state.get(f"draft_for_message_{m.id}", ""),
                                    key=f"draftarea-{m.id}",
                                    height=200,
                                )
                                col_send, col_cancel = st.columns([1, 1])
                                with col_send:
                                    if st.button(f"Send draft for message {m.id}", key=f"send-draft-{m.id}"):
                                        # persist draft and mark sent
                                        # try to include any provided values stored in session_state
                                        cust = st.session_state.get(f"cust_values_{sug.id}") if sug else None
                                        resp = st.session_state.get(f"resp_values_{sug.id}") if sug else None
                                        d = create_email_draft(
                                            db=db,
                                            thread_id=t.id,
                                            body=draft_val,
                                            message_id=m.id,
                                            suggestion_id=sug.id,
                                            customer_provided=cust,
                                            responder_provided=resp,
                                            status="draft",
                                        )
                                        mark_draft_sent(db=db, draft_id=d.id)
                                        # immediate UI flag so Respond shows 'Sent'
                                        st.session_state[f"sent_for_message_{m.id}"] = True
                                        st.success("Draft sent and persisted")
                                        # remove draft from session state
                                        del st.session_state[f"draft_for_message_{m.id}"]
                                with col_cancel:
                                    if st.button(f"Cancel draft {m.id}", key=f"cancel-draft-{m.id}"):
                                        del st.session_state[f"draft_for_message_{m.id}"]
                        else:
                            # Only show this line when there truly is no AI suggestion
                            if not sug:
                                st.write("No AI suggestion for this message.")

                    # Override handled inline in the action row above

                    # Show accepted marker if session_state or DB indicates acceptance
                    accepted_flag = st.session_state.get(f"accepted_suggestion_{sug.id}") if sug else False
                    try:
                        if sug and not accepted_flag:
                            # check DB in case decision was recorded in another session
                            accepted_flag = has_accepted_decision_for_suggestion(db=db, suggestion_id=sug.id)
                    except Exception:
                        pass
                    # Only render the final accepted info if it's accepted and not already shown via the Accept badge
                    if accepted_flag and not st.session_state.get(f"accepted_suggestion_{sug.id}", False):
                        st.info("Suggestion accepted")

                # allow re-evaluating suggestions using the rule engine (useful when AI integration is unavailable)
                # If any message in the thread has a sent draft, hide the re-evaluate button
                thread_has_sent = any(st.session_state.get(f"sent_for_message_{mm.id}") or False for mm in msgs) or any(
                    has_sent_draft_for_message(db=db, message_id=mm.id) for mm in msgs
                )
                if not thread_has_sent and st.button(
                    f"Re-evaluate suggestions for thread {t.id}", key=f"reeval-{t.id}"
                ):
                    for m in msgs:
                        latest = get_latest_suggestion_for_message(db, m.id)
                        should_create = False

                        # First: try AI once
                        try:
                            ai_resp = get_intent([{"role": "user", "content": m.body}])
                            intent = getattr(ai_resp, "intent", "unknown")
                            confidence = getattr(ai_resp, "confidence", 0.0)
                        except Exception:
                            intent = "unknown"
                            confidence = 0.0

                        suggested_action = "no-action"
                        # If AI failed or returned unknown/zero confidence, fallback to rule-based
                        if intent == "unknown" or confidence <= 0.0:
                            r_intent, r_conf, r_action = rule_based_intent_and_action(m.body)
                            intent = r_intent
                            confidence = r_conf
                            suggested_action = r_action
                        else:
                            # map AI intent to action (same mapping used elsewhere)
                            if intent == "interested":
                                suggested_action = "send_pricing"
                            elif intent == "not_interested":
                                suggested_action = "close_thread"

                        # Decide whether to persist new suggestion
                        if latest is None:
                            should_create = True
                        else:
                            try:
                                if confidence > (latest.confidence or 0.0):
                                    should_create = True
                            except Exception:
                                should_create = True

                            if should_create and confidence > 0.0:
                                # try to extract extra fields from the AI response if available
                                try:
                                    required_fields = getattr(ai_resp, "required_fields", None)
                                    follow_up_question = getattr(ai_resp, "follow_up_question", None)
                                except Exception:
                                    required_fields = None
                                    follow_up_question = None
                                # serialize raw ai response for provenance
                                raw_resp = None
                                try:
                                    import json as _json

                                    if hasattr(ai_resp, "dict"):
                                        raw_resp = _json.dumps(ai_resp.dict(), default=str)
                                    else:
                                        raw_resp = _json.dumps(ai_resp, default=str)
                                except Exception:
                                    try:
                                        raw_resp = str(ai_resp)
                                    except Exception:
                                        raw_resp = None
                                create_ai_suggestion(
                                    db=db,
                                    message_id=mm.id,
                                    intent=intent,
                                    confidence=confidence,
                                    suggested_action=suggested_action,
                                    required_fields=required_fields,
                                    follow_up_question=follow_up_question,
                                    raw_response=raw_resp,
                                )
                    st.success("Re-evaluated suggestions for this thread — refresh to see updates")

        # Show recent in-memory logs for debugging
        with st.expander("App Logs (recent)"):
            logs = get_recent_logs()
            if logs:
                for line in logs[-200:]:
                    st.text(line)
            else:
                st.write("No logs captured yet.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
