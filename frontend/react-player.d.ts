declare module 'react-player' {
    import { Component } from 'react';

    interface ReactPlayerProps {
        url?: string;
        playing?: boolean;
        loop?: boolean;
        controls?: boolean;
        light?: boolean | string;
        volume?: number;
        muted?: boolean;
        playbackRate?: number;
        width?: string | number;
        height?: string | number;
        style?: React.CSSProperties;
        progressInterval?: number;
        playsinline?: boolean;
        pip?: boolean;
        stopOnUnmount?: boolean;
        fallback?: React.ReactElement;
        wrapper?: string | React.ComponentType<{ children: React.ReactNode }>;
        config?: Record<string, unknown>;
        onReady?: (player: ReactPlayer) => void;
        onStart?: () => void;
        onPlay?: () => void;
        onPause?: () => void;
        onBuffer?: () => void;
        onEnded?: () => void;
        onError?: (error: unknown) => void;
    }

    class ReactPlayer extends Component<ReactPlayerProps> {}
    export default ReactPlayer;
}
