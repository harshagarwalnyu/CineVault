"""
Knowledge Graph Engine (PhD Upgrade)
=====================================
Constructs a heterogeneous graph of Movies, Actors, Directors, and Genres.
Uses NetworkX for graph traversals and community detection.
"""

import networkx as nx
import pandas as pd
from typing import List, Dict
import community.community_louvain as community_louvain  # python-louvain

from backend.services.recommendation_engine_service.engines.recommendation import (
    normalize_genres,
    split_genres,
)


class KnowledgeGraph:
    def __init__(self):
        self.graph = nx.Graph()
        self.is_built = False

    def build_graph(self, limit: int = 5000):
        """Build the knowledge graph from the database."""
        # Use SQLAlchemy text for parameterization
        from sqlmodel import text
        from backend.database import engine

        query = text("""
            SELECT id, title, "cast", director, genres, vote_average
            FROM movies
            WHERE vote_count > 50
            LIMIT :limit
        """)
        with engine.connect() as conn:
            df = pd.read_sql_query(query, conn, params={"limit": limit})

        for _, row in df.iterrows():
            movie_id = f"movie:{row['id']}"
            self.graph.add_node(
                movie_id, type="movie", title=row["title"], rating=row["vote_average"]
            )

            # Add Director
            if pd.notna(row["director"]) and isinstance(row["director"], str) and row["director"].strip():
                director_name = row["director"].strip()
                director_id = f"director:{director_name}"
                self.graph.add_node(director_id, type="director", name=director_name)
                self.graph.add_edge(
                    movie_id, director_id, weight=1.0, relation="directed_by"
                )

            # Add Cast (Top 3)
            if pd.notna(row["cast"]) and isinstance(row["cast"], str) and row["cast"].strip():
                actors = [a.strip() for a in row["cast"].split(",")[:3]]
                for actor in actors:
                    actor_id = f"actor:{actor}"
                    self.graph.add_node(actor_id, type="actor", name=actor)
                    self.graph.add_edge(
                        movie_id, actor_id, weight=0.8, relation="acted_in"
                    )

            # Add Genres
            if pd.notna(row["genres"]) and row["genres"]:
                genres = split_genres(normalize_genres(str(row["genres"])))
                for genre in genres:
                    genre_id = f"genre:{genre}"
                    self.graph.add_node(genre_id, type="genre", name=genre)
                    self.graph.add_edge(
                        movie_id, genre_id, weight=0.5, relation="has_genre"
                    )

        self.is_built = True
        print(
            f"Graph built: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges."
        )

    def find_paths(
        self, movie_title_1: str, movie_title_2: str, max_depth: int = 3
    ) -> List[List[str]]:
        """Find connection paths between two movies (e.g., shared actor)."""
        if not self.is_built:
            self.build_graph()

        # Find nodes
        node1 = None
        node2 = None

        # Inefficient linear search, but fine for small graphs (production would use an index)
        for n, data in self.graph.nodes(data=True):
            if data.get("type") == "movie":
                if data.get("title", "").lower() == movie_title_1.lower():
                    node1 = n
                elif data.get("title", "").lower() == movie_title_2.lower():
                    node2 = n

        if not node1 or not node2:
            return []

        try:
            paths = list(nx.all_shortest_paths(self.graph, node1, node2))
            # Format paths for display
            readable_paths = []
            for path in paths:
                readable = []
                for node in path:
                    data = self.graph.nodes[node]
                    name = data.get("title") or data.get("name")
                    readable.append(f"{data['type'].title()}: {name}")
                readable_paths.append(readable)
            return readable_paths
        except nx.NetworkXNoPath:
            return []

    def get_related_entities(
        self, movie_title: str, entity_type: str = "movie", limit: int = 5
    ) -> List[Dict]:
        """Get related entities via random walks or neighbor analysis."""
        if not self.is_built:
            self.build_graph()

        start_node = None
        for n, data in self.graph.nodes(data=True):
            if (
                data.get("type") == "movie"
                and data.get("title", "").lower() == movie_title.lower()
            ):
                start_node = n
                break

        if not start_node:
            return []

        # Get neighbors of neighbors (2 hops)
        related = {}
        for neighbor in self.graph.neighbors(start_node):
            for second_neighbor in self.graph.neighbors(neighbor):
                if second_neighbor == start_node:
                    continue

                node_data = self.graph.nodes[second_neighbor]
                if node_data["type"] == entity_type:
                    if second_neighbor not in related:
                        related[second_neighbor] = 0
                    # Weight by path strength
                    w1 = self.graph[start_node][neighbor]["weight"]
                    w2 = self.graph[neighbor][second_neighbor]["weight"]
                    related[second_neighbor] += w1 * w2

        # Sort and format
        sorted_nodes = sorted(related.items(), key=lambda x: x[1], reverse=True)[:limit]
        results = []
        for node_id, score in sorted_nodes:
            data = self.graph.nodes[node_id]
            results.append(
                {
                    "name": data.get("title") or data.get("name"),
                    "type": data["type"],
                    "connection_strength": round(score, 2),
                }
            )

        return results

    def detect_communities(self) -> Dict[str, int]:
        """Detect communities (clusters) in the movie graph using Louvain method."""
        if not self.is_built:
            self.build_graph()

        # Partition based on modularity
        partition = community_louvain.best_partition(self.graph)
        return partition


# Singleton
_kg = None


def get_knowledge_graph():
    global _kg
    if _kg is None:
        _kg = KnowledgeGraph()
    return _kg


if __name__ == "__main__":
    kg = get_knowledge_graph()
    kg.build_graph(limit=100)
    print("Related to 'The Dark Knight':", kg.get_related_entities("The Dark Knight"))
