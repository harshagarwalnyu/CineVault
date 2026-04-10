'use client';

import dynamic from 'next/dynamic';

const ReactPlayer = dynamic(() => import('react-player'), { ssr: false });

interface Props {
    youtubeKey: string;
}

export default function TrailerEmbed({ youtubeKey }: Props) {
    if (!youtubeKey) return null;

    return (
        <div className="aspect-video rounded-lg overflow-hidden bg-black">
            <ReactPlayer
                url={`https://www.youtube.com/watch?v=${youtubeKey}`}
                width="100%"
                height="100%"
                controls
                light
            />
        </div>
    );
}
