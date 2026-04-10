'use client';

import TimeMachine from '../../components/TimeMachine';

export default function TimeMachinePage() {
    return (
        <div className="min-h-screen bg-[#0a0a0a] text-white p-6 max-w-7xl mx-auto">
            <h1 className="text-3xl font-bold mb-6">Time Machine</h1>
            <p className="text-white/60 mb-6">Travel through decades of cinema history</p>
            <TimeMachine />
        </div>
    );
}
