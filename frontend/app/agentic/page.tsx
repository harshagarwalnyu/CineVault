"use client";

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, Play, ArrowRight } from 'lucide-react';

type Availability = {
  status: string;
  primary_action?: {
    type: string;
    platform: { id: string; name: string; color: string; icon: string };
    deep_link: string;
    cost: number;
    label: string;
  };
};

type Recommendation = {
  title: string;
  overview: string;
  match_score: number;
  why_you_will_like_it: any[];
  availability?: Availability;
};

type AgenticResponse = {
  intent_understood: any;
  graph_nodes_activated: string[];
  ui_state: 'single_focus_hero' | 'detail_cards' | 'comparison_grid';
  recommendations: Recommendation[];
};

export default function AgenticDiscovery() {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AgenticResponse | null>(null);
  const [isListening, setIsListening] = useState(false);

  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setResult(null);

    try {
      const response = await fetch('/api/v1/discovery/agentic', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
      });
      const data = await response.json();
      setResult(data);
    } catch (error) {
      console.error('Agentic Discovery Error:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleVoice = () => {
    // Simple Web Speech API integration for Phase 4
    if (!('webkitSpeechRecognition' in window)) {
      alert("Your browser doesn't support speech recognition.");
      return;
    }

    const SpeechRecognition = (window as any).webkitSpeechRecognition;
    const recognition = new SpeechRecognition();

    recognition.onstart = () => setIsListening(true);
    recognition.onresult = (event: any) => {
      const transcript = event.results[0][0].transcript;
      setQuery(transcript);
      // Auto-submit after voice
      setTimeout(() => {
        const form = document.getElementById('agentic-form');
        if (form) form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
      }, 500);
    };
    recognition.onend = () => setIsListening(false);

    recognition.start();
  };

  // Intent Blocks
  const SingleFocusHero = ({ rec }: { rec: Recommendation }) => (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="flex flex-col items-center justify-center h-full min-h-[60vh] text-center max-w-4xl mx-auto p-8"
    >
      <h2 className="text-6xl font-black mb-6 tracking-tighter bg-gradient-to-r from-purple-400 to-pink-600 text-transparent bg-clip-text">
        {rec.title}
      </h2>
      <p className="text-2xl text-gray-300 mb-12 leading-relaxed">{rec.overview}</p>

      {/* Explainability Payload (Neurosymbolic Node) */}
      <div className="flex flex-wrap gap-4 justify-center mb-12">
        {rec.why_you_will_like_it?.map((reason, idx) => (
          <span key={idx} className="px-4 py-2 bg-purple-900/30 text-purple-200 border border-purple-500/30 rounded-full text-sm font-medium backdrop-blur-md">
            {reason.trope}: {reason.explanation}
          </span>
        ))}
      </div>

      {/* The Zero-Click Moat */}
      {rec.availability?.primary_action && (
        <a
          href={rec.availability.primary_action.deep_link}
          target="_blank"
          className="group relative inline-flex items-center justify-center px-12 py-6 text-xl font-bold text-white transition-all duration-200"
        >
          <div className="absolute inset-0 w-full h-full border-2 border-white/20 rounded-2xl group-hover:bg-white/5 transition-all"></div>
          <Play className="w-6 h-6 mr-3 fill-current" />
          {rec.availability.primary_action.label}
        </a>
      )}
    </motion.div>
  );

  const DetailCards = ({ recs }: { recs: Recommendation[] }) => (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 p-8 max-w-7xl mx-auto">
      {recs.map((rec, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.1 }}
          className="bg-gray-900/50 border border-gray-800 rounded-3xl p-6 hover:border-purple-500/50 transition-all group relative overflow-hidden"
        >
          <div className="absolute inset-0 bg-gradient-to-br from-purple-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity"></div>
          <h3 className="text-2xl font-bold mb-4">{rec.title}</h3>
          <p className="text-gray-400 text-sm line-clamp-3 mb-6">{rec.overview}</p>

          {rec.availability?.primary_action && (
            <a
              href={rec.availability.primary_action.deep_link}
              target="_blank"
              className="flex w-full items-center justify-center py-3 bg-white/10 hover:bg-white/20 rounded-xl font-medium transition-colors mt-auto"
            >
              {rec.availability.primary_action.label}
            </a>
          )}
        </motion.div>
      ))}
    </div>
  );

  return (
    <div className="min-h-screen bg-black text-white selection:bg-purple-500/30 font-sans">
      {/* Dynamic Header/Search Bar */}
      <motion.div
        layout
        className={`w-full max-w-3xl mx-auto p-6 flex flex-col items-center ${result ? 'pt-8' : 'pt-[30vh]'}`}
      >
        <motion.h1
          layout="position"
          className="text-4xl font-light tracking-tight mb-8 text-center"
        >
          What's your <span className="font-semibold italic text-purple-400">vibe</span> tonight?
        </motion.h1>

        <form id="agentic-form" onSubmit={handleSearch} className="w-full relative flex items-center">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g., A funny heist movie, but not too stressful..."
            className="w-full bg-white/5 border border-white/10 rounded-full px-8 py-5 text-lg outline-none focus:border-purple-500/50 focus:bg-white/10 transition-all placeholder:text-gray-600 backdrop-blur-xl pr-32"
          />
          <div className="absolute right-4 flex items-center gap-2">
            <button
              type="button"
              onClick={handleVoice}
              className={`p-3 rounded-full transition-colors ${isListening ? 'bg-red-500/20 text-red-500 animate-pulse' : 'hover:bg-white/10 text-gray-400'}`}
            >
              <Mic className="w-5 h-5" />
            </button>
            <button
              type="submit"
              disabled={loading}
              className="p-3 bg-white text-black rounded-full hover:scale-105 transition-transform disabled:opacity-50 disabled:hover:scale-100"
            >
              {loading ? <div className="w-5 h-5 border-2 border-black/20 border-t-black rounded-full animate-spin" /> : <ArrowRight className="w-5 h-5" />}
            </button>
          </div>
        </form>
      </motion.div>

      {/* Generative UI Rendering Area */}
      <AnimatePresence mode="wait">
        {result && (
          <motion.div
            key="results"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="w-full"
          >
            {/* The Generative 'Liquid' UI Switch */}
            {result.recommendations.length === 0 ? (
              <div className="text-center p-12 text-gray-500">Could not find a match for that specific vibe. Try something else.</div>
            ) : result.ui_state === 'single_focus_hero' ? (
              <SingleFocusHero rec={result.recommendations[0]} />
            ) : (
              <DetailCards recs={result.recommendations} />
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
