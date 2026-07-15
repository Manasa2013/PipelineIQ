"""
LangGraph graph builder for PipelineIQ.

Defines the pipeline graph with nodes, edges, and conditional routing
based on the classification output.
"""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from backend.agents.classification_agent import classification_agent
from backend.agents.email_tool_node import email_tool_node
from backend.agents.enrichment_agent import enrichment_agent
from backend.agents.human_approval_node import human_approval_node
from backend.agents.intake_agent import intake_agent
from backend.agents.outreach_agent import outreach_agent
from backend.agents.scoring_agent import scoring_agent
from backend.graph.state import PipelineState


# ── Node labels ─────────────────────────────────────────────────────────

NODE_INTAKE = "agent__intake"
NODE_ENRICHMENT = "agent__enrichment"
NODE_SCORING = "agent__scoring"
NODE_CLASSIFICATION = "agent__classification"
NODE_OUTREACH = "agent__outreach"
NODE_HUMAN_APPROVAL = "agent__human_approval"
NODE_EMAIL_TOOL = "agent__email_tool"


# ── Conditional routing ────────────────────────────────────────────────


def route_after_classification(state: PipelineState) -> str:
    """
    Route to the next node based on the classification category.

    - "hot"        → outreach (generate draft email)
    - "nurture"    → END (terminate, lead goes to nurture campaign)
    - "disqualify" → END (terminate, lead is disqualified)
    - default      → END (safety fallback)

    Args:
        state: Current pipeline state.

    Returns:
        The name of the next node to execute.
    """
    classification = state.get("classification", {})
    category = classification.get("category", "").strip().lower()

    if category == "hot":
        return NODE_OUTREACH
    elif category == "nurture":
        return END
    elif category == "disqualify":
        return END
    else:
        return END


# ── Graph builder ──────────────────────────────────────────────────────


def build_pipeline_graph() -> StateGraph:
    """
    Construct and compile the PipelineIQ LangGraph.

    Graph flow::

        START
          │
          ▼
        intake ──► enrichment ──► scoring ──► classification
                                                  │
                                          ┌───────┼───────┐
                                          │       │       │
                                          ▼       ▼       ▼
                                        hot   nurture  disqualify
                                          │       │       │
                                          ▼       ▼       ▼
                                      outreach    END      END
                                          │
                                          ▼
                                    human_approval
                                          │
                                          ▼
                                      email_tool
                                          │
                                          ▼
                                         END

    Returns:
        A compiled StateGraph ready to be invoked.
    """
    builder = StateGraph(state_schema=PipelineState)

    # ── Register all nodes ─────────────────────────────────────────────
    builder.add_node(NODE_INTAKE, intake_agent)
    builder.add_node(NODE_ENRICHMENT, enrichment_agent)
    builder.add_node(NODE_SCORING, scoring_agent)
    builder.add_node(NODE_CLASSIFICATION, classification_agent)
    builder.add_node(NODE_OUTREACH, outreach_agent)
    builder.add_node(NODE_HUMAN_APPROVAL, human_approval_node)
    builder.add_node(NODE_EMAIL_TOOL, email_tool_node)

    # ── Linear pipeline (always executed) ──────────────────────────────
    builder.set_entry_point(NODE_INTAKE)
    builder.add_edge(NODE_INTAKE, NODE_ENRICHMENT)
    builder.add_edge(NODE_ENRICHMENT, NODE_SCORING)
    builder.add_edge(NODE_SCORING, NODE_CLASSIFICATION)

    # ── Conditional routing after classification ───────────────────────
    builder.add_conditional_edges(
        NODE_CLASSIFICATION,
        route_after_classification,
        {
            NODE_OUTREACH: NODE_OUTREACH,
            END: END,
        },
    )

    # ── Hot-path: outreach → approval → email tool → END ───────────────
    builder.add_edge(NODE_OUTREACH, NODE_HUMAN_APPROVAL)
    builder.add_edge(NODE_HUMAN_APPROVAL, NODE_EMAIL_TOOL)
    builder.add_edge(NODE_EMAIL_TOOL, END)

    # ── Compile with checkpointer (required for interrupt/human-in-the-loop) ──
    checkpointer = MemorySaver()
    graph = builder.compile(checkpointer=checkpointer)
    return graph


# Singleton instance
pipeline_graph = build_pipeline_graph()