'use client';

import { use } from 'react';
import DirectorJourney from '../../../components/DirectorJourney';

export default function DirectorPage({ params }: { params: Promise<{ name: string }> }) {
    const { name } = use(params);

    return (
        <div className="min-h-screen bg-[#0a0a0a] text-white p-6 max-w-4xl mx-auto">
            <DirectorJourney directorName={decodeURIComponent(name)} />
        </div>
    );
}
