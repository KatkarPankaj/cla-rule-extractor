from langgraph.graph import StateGraph, START, END
from .state import WorkflowState
from .nodes import ingest_node, index_node, retrieve_node, analyze_node, evidence_node, verify_node

def build_workflow():
    g = StateGraph(WorkflowState)

    g.add_node("ingest", ingest_node)
    g.add_node("index", index_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("analyze", analyze_node)
    g.add_node("evidence", evidence_node)
    g.add_node("verify", verify_node)

    g.add_edge(START, "ingest")
    g.add_edge("ingest", "index")
    g.add_edge("index", "retrieve")
    g.add_edge("retrieve", "analyze")
    g.add_edge("analyze", "evidence")
    g.add_edge("evidence", "verify")
    g.add_edge("verify", END)

    return g.compile()
