from langgraph.graph import StateGraph, START, END
from graph.state import ResearchState

# ingestion nodes
from nodes.pdf_parser import pdf_parser
from nodes.embedder import embedder
from nodes.metadata_extractor import metadata_extractor
from nodes.summarizer import summarizer
from nodes.gap_finder import gap_finder

# query nodes
from nodes.chunk_loader import chunk_loader
from nodes.query_router import query_router
from nodes.retriever import retriever
from nodes.grader import grader
from nodes.web_search import web_search
from nodes.generator import generator
from nodes.citation_builder import citation_builder


def route_grader(state: ResearchState) -> str:
    if state['web_search_triggered']:
        return 'web_search'
    return 'generator'


def build_ingestion_graph():
    graph = StateGraph(ResearchState)

    graph.add_node('pdf_parser', pdf_parser)
    graph.add_node('embedder', embedder)
    graph.add_node('metadata_extractor', metadata_extractor)
    graph.add_node('summarizer', summarizer)
    graph.add_node('gap_finder', gap_finder)

    graph.add_edge(START, 'pdf_parser')
    graph.add_edge('pdf_parser', 'embedder')
    graph.add_edge('embedder', 'metadata_extractor')
    graph.add_edge('metadata_extractor', 'summarizer')
    graph.add_edge('summarizer', 'gap_finder')
    graph.add_edge('gap_finder', END)

    return graph.compile()


def build_query_graph():
    graph = StateGraph(ResearchState)

    graph.add_node('chunk_loader', chunk_loader)
    graph.add_node('query_router', query_router)
    graph.add_node('retriever', retriever)
    graph.add_node('grader', grader)
    graph.add_node('web_search', web_search)
    graph.add_node('generator', generator)
    graph.add_node('citation_builder', citation_builder)

    graph.add_edge(START, 'chunk_loader')
    graph.add_edge('chunk_loader', 'query_router')
    graph.add_edge('query_router', 'retriever') 
    graph.add_edge('retriever', 'grader')

    graph.add_conditional_edges('grader', route_grader, {
        'web_search': 'web_search',
        'generator': 'generator'
    })

    graph.add_edge('web_search', 'generator')
    graph.add_edge('generator', 'citation_builder')
    graph.add_edge('citation_builder', END)

    return graph.compile()