'use client';

import { useRouter } from 'next/navigation';
import OnboardingFlow from '../../components/OnboardingFlow';

export default function OnboardingPage() {
    const router = useRouter();
    // TODO: get actual user ID from auth
    const userId = 1;

    return (
        <div className="min-h-screen bg-[#0a0a0a] text-white p-6 max-w-7xl mx-auto">
            <OnboardingFlow userId={userId} onComplete={() => router.push('/')} />
        </div>
    );
}
