'use client';

import { useEffect, useState } from 'react';
import { movieApi } from '../api';

interface Props {
    movieId: number;
}

interface GraphNode {
    id: string;
    name: string;
    type: string;
}

interface GraphLink {
    source: string;
    target: string;
    relation: string;
}

export default function MovieConnections({ movieId }: Props) {
    const [nodes, setNodes] = useState<GraphNode[]>([]);
    const [links, setLinks] = useState<GraphLink[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        movieApi.getMovieConnections(movieId)
            .then((data) => {
                const related = data?.related || [];
                const nodeMap = new Map<string, GraphNode>();
                const linkList: GraphLink[] = [];

                nodeMap.set(`movie_${movieId}`, { id: `movie_${movieId}`, name: 'This Movie', type: 'movie' });

                for (const item of related) {
                    const nodeId = `${item.type}_${item.name}`;
                    if (!nodeMap.has(nodeId)) {
                        nodeMap.set(nodeId, { id: nodeId, name: item.name, type: item.type || 'entity' });
                    }
                    linkList.push({ source: `movie_${movieId}`, target: nodeId, relation: item.relation || 'related' });
                }

                setNodes(Array.from(nodeMap.values()));
                setLinks(linkList);
            })
            .catch(() => {})
            .finally(() => setLoading(false));
    }, [movieId]);

    if (loading) return <div className="text-white/50">Loading connections...</div>;
    if (nodes.length <= 1) return <div className="text-white/50">No connections found</div>;

    // Simple list-based visualization (graph library is optional dep)
    return (
        <div className="space-y-3">
            <h3 className="text-lg font-semibold text-white">Connections ({nodes.length - 1})</h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {nodes.filter(n => n.id !== `movie_${movieId}`).map((node) => {
                    const link = links.find(l => l.target === node.id);
                    return (
                        <div key={node.id} className="p-2 bg-white/5 rounded-lg">
                            <p className="text-sm text-white/80">{node.name}</p>
                            <p className="text-xs text-white/40 capitalize">{node.type} - {link?.relation}</p>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
