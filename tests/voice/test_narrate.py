"""write_exit_interview: the key-free fallback must be deterministic AND
grounded in the persona's real trace (actual captions + outcome)."""

from ghostpanel_contracts import PersonaOutcome, PersonaResult

from ghostpanel.voice.narrate import template_exit_interview, write_exit_interview


async def test_fallback_references_real_captions_and_outcome(grandma_result, grandma_persona):
    text = await write_exit_interview(grandma_result, grandma_persona, anthropic_key=None)
    # Grounded: quotes the actual decoy-button caption from the trace...
    assert "Explore plans" in text
    # ...and the recorded failure reason (the decoy expectation)
    assert "decoy" in text
    # ...and reflects the STUCK outcome in first person
    assert "I gave up" in text


async def test_fallback_is_deterministic(grandma_result, grandma_persona):
    first = await write_exit_interview(grandma_result, grandma_persona)
    second = await write_exit_interview(grandma_result, grandma_persona)
    assert first == second == template_exit_interview(grandma_result, grandma_persona)


async def test_fallback_success_tone(power_user_result, grandma_persona):
    text = await write_exit_interview(power_user_result, grandma_persona)
    assert "I got it done" in text


def test_templates_cover_every_outcome(grandma_result, grandma_persona):
    for outcome in PersonaOutcome:
        result = grandma_result.model_copy(update={"outcome": outcome})
        text = template_exit_interview(result, grandma_persona)
        assert text.strip(), f"empty template for {outcome}"


def test_step_budget_template_mentions_step_count(grandma_persona):
    result = PersonaResult(
        persona_id="grandma-72",
        outcome=PersonaOutcome.STEP_BUDGET,
        failure_reason="Hit the 30 step budget.",
    )
    text = template_exit_interview(result, grandma_persona)
    assert "ran out of patience" in text
    assert "Hit the 30 step budget." in text
