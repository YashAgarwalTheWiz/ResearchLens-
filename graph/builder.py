from langgraph.graph import StateGraph, START, END

from graph.state import ResearchState
from graph.positioning_state import PositioningState

# ingestion nodes
from nodes.pdf_parser import pdf_parser
from nodes.embedder import embedder
from nodes.table_extractor import table_extractor
from nodes.extractor import extractor

# question-answering nodes
from nodes.retriever import retriever
from nodes.generator import generator
from nodes.citation_builder import citation_builder

# positioning nodes
from nodes.related_finder import related_finder
from nodes.related_extractor import related_extractor
from nodes.positioning_analyst import positioning_analyst
from nodes.citation_verifier import citation_verifier


def stop_on_error(state) -> str:
    return 'stop' if state.get('error') else 'go'


def build_ingestion_graph():
    """PDF -> chunks -> embeddings -> tables -> grounded facts (every fact carries a page + quote)."""
    graph = StateGraph(ResearchState)

    graph.add_node('pdf_parser', pdf_parser)
    graph.add_node('embedder', embedder)
    graph.add_node('table_extractor', table_extractor)
    graph.add_node('extractor', extractor)

    graph.add_edge(START, 'pdf_parser')
    graph.add_edge('pdf_parser', 'embedder')
    graph.add_edge('embedder', 'table_extractor')
    graph.add_edge('table_extractor', 'extractor')
    graph.add_edge('extractor', END)

    return graph.compile()


def build_query_graph():
    """Question -> top chunks -> answer with [S1] citations -> keep only real citations."""
    graph = StateGraph(ResearchState)

    graph.add_node('retriever', retriever)
    graph.add_node('generator', generator)
    graph.add_node('citation_builder', citation_builder)

    graph.add_edge(START, 'retriever')
    graph.add_edge('retriever', 'generator')
    graph.add_edge('generator', 'citation_builder')
    graph.add_edge('citation_builder', END)

    return graph.compile()


def build_positioning_graph():
    """Our paper -> related papers (OpenAlex) -> comparison table -> novelty + gaps -> verified citations."""
    graph = StateGraph(PositioningState)

    graph.add_node('related_finder', related_finder)
    graph.add_node('related_extractor', related_extractor)
    graph.add_node('positioning_analyst', positioning_analyst)
    graph.add_node('citation_verifier', citation_verifier)

    graph.add_edge(START, 'related_finder')
    graph.add_conditional_edges('related_finder', stop_on_error, {'stop': END, 'go': 'related_extractor'})
    graph.add_conditional_edges('related_extractor', stop_on_error, {'stop': END, 'go': 'positioning_analyst'})
    graph.add_conditional_edges('positioning_analyst', stop_on_error, {'stop': END, 'go': 'citation_verifier'})
    graph.add_edge('citation_verifier', END)

    return graph.compile()