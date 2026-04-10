'use client';

import TasteFingerprint from '../../components/TasteFingerprint';

export default function TastePage() {
    // TODO: get actual user ID from auth
    const userId = 1;

    return (
        <div className="min-h-screen bg-[#0a0a0a] text-white p-6 max-w-3xl mx-auto">
            <h1 className="text-3xl font-bold mb-6">Your Taste Fingerprint</h1>
            <TasteFingerprint userId={userId} />
        </div>
    );
}
