'use client';

interface WatchEntry {
    movie_id: number;
    title: string;
    poster_path?: string;
    watched_at: string;
}

interface Props {
    entries: WatchEntry[];
}

export default function WatchTimeline({ entries }: Props) {
    if (!entries.length) return <p className="text-white/50">No watch history yet</p>;

    return (
        <div className="flex gap-4 overflow-x-auto pb-2">
            {entries.map((entry, i) => (
                <div key={`${entry.movie_id}-${i}`} className="flex-shrink-0 w-24 text-center">
                    <div className="aspect-[2/3] rounded bg-white/5 overflow-hidden">
                        {entry.poster_path ? (
                            <img src={`https://image.tmdb.org/t/p/w200${entry.poster_path}`} alt={entry.title} className="w-full h-full object-cover" />
                        ) : (
                            <div className="w-full h-full flex items-center justify-center text-white/20 text-[10px]">{entry.title}</div>
                        )}
                    </div>
                    <p className="text-[10px] text-white/50 mt-1">{entry.watched_at?.slice(0, 10)}</p>
                </div>
            ))}
        </div>
    );
}
