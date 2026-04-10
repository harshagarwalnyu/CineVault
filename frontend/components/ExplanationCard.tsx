'use client';

interface Props {
    reason: string;
    scores?: Record<string, number>;
}

export default function ExplanationCard({ reason, scores }: Props) {
    const activeScores = scores
        ? Object.entries(scores).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).slice(0, 4)
        : [];

    return (
        <div className="mt-2 space-y-1">
            {reason && (
                <p className="text-sm text-white/70 italic">{reason}</p>
            )}
            {activeScores.length > 0 && (
                <div className="flex flex-wrap gap-1">
                    {activeScores.map(([key, value]) => (
                        <span
                            key={key}
                            className="text-xs px-2 py-0.5 rounded-full bg-white/10 text-white/60"
                        >
                            {key.replace(/_/g, ' ')}: {value}
                        </span>
                    ))}
                </div>
            )}
        </div>
    );
}
