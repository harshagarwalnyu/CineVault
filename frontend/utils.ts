import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

import { TMDB_IMAGE_BASE } from './constants';

export const formatMatchScore = (voteAverage: number): string => {
    const normalizedScore = voteAverage <= 1 ? voteAverage * 100 : voteAverage * 10;
    return `${Math.round(normalizedScore)}% Match`;
};

export const cn = (...inputs: ClassValue[]): string => twMerge(clsx(inputs));

const svgToDataUri = (svg: string): string =>
    `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;

export type ArtworkVariant = 'poster' | 'backdrop';

type ArtworkMovie = {
    title?: string;
    poster_path?: string;
    backdrop_path?: string;
};

const normalizeTmdbPath = (path?: string | null): string | null => {
    if (!path) return null;
    if (path.startsWith('http')) return path;
    return path.startsWith('/') ? path : `/${path}`;
};

const createFallbackArtwork = (
    title: string,
    variant: ArtworkVariant,
): string => {
    const safeTitle = (title || 'CineVault').slice(0, 28);
    const width = variant === 'poster' ? 900 : 1600;
    const height = variant === 'poster' ? 1350 : 900;
    const label = variant === 'poster' ? 'Editorial Pick' : 'Cinema Feed';
    return svgToDataUri(`
        <svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
            <defs>
                <linearGradient id="bg" x1="0%" x2="100%" y1="0%" y2="100%">
                    <stop offset="0%" stop-color="#09090b"/>
                    <stop offset="55%" stop-color="#121116"/>
                    <stop offset="100%" stop-color="#251a1b"/>
                </linearGradient>
                <radialGradient id="glow" cx="75%" cy="20%" r="60%">
                    <stop offset="0%" stop-color="#f2c14f" stop-opacity="0.55"/>
                    <stop offset="100%" stop-color="#f2c14f" stop-opacity="0"/>
                </radialGradient>
            </defs>
            <rect width="${width}" height="${height}" fill="url(#bg)"/>
            <rect width="${width}" height="${height}" fill="url(#glow)"/>
            <rect x="36" y="36" width="${width - 72}" height="${height - 72}" rx="30" fill="none" stroke="#5d4f2b" stroke-width="3" opacity="0.85"/>
            <text x="72" y="120" fill="#f2c14f" font-family="Georgia, serif" font-size="${variant === 'poster' ? 34 : 28}" letter-spacing="4">${label.toUpperCase()}</text>
            <text x="72" y="${variant === 'poster' ? 760 : 480}" fill="#f5efe2" font-family="Georgia, serif" font-size="${variant === 'poster' ? 72 : 88}" font-weight="700">${safeTitle}</text>
            <text x="72" y="${variant === 'poster' ? 840 : 570}" fill="#b8aea0" font-family="Helvetica, Arial, sans-serif" font-size="${variant === 'poster' ? 24 : 26}">
                Curated by CineVault
            </text>
        </svg>
    `);
};

const buildTmdbImage = (
    path: string | null,
    width: 'w500' | 'w780' | 'w1280' | 'original',
): string | null => {
    if (!path) return null;
    if (path.startsWith('http')) return path;
    return `${TMDB_IMAGE_BASE}${width}${path}`;
};

const unique = (values: Array<string | null | undefined>): string[] =>
    Array.from(new Set(values.filter((value): value is string => Boolean(value))));

export const getImageUrl = (
    path: string | undefined,
    title: string,
    width: 'w500' | 'w780' | 'w1280' | 'original' = 'w500',
): string => {
    const image = buildTmdbImage(normalizeTmdbPath(path), width);
    return image ?? createFallbackArtwork(title, 'poster');
};

export const resolveMovieArtwork = (
    movie: ArtworkMovie,
    variant: ArtworkVariant,
    attempt = 0,
): { src: string; alt: string; isFallback: boolean } => {
    const title = movie.title || 'CineVault';
    const poster = buildTmdbImage(normalizeTmdbPath(movie.poster_path), 'w780');
    const backdrop = buildTmdbImage(normalizeTmdbPath(movie.backdrop_path), 'w1280');
    const candidates = variant === 'poster'
        ? unique([poster, backdrop, createFallbackArtwork(title, 'poster')])
        : unique([backdrop, poster, createFallbackArtwork(title, 'backdrop')]);
    const src = candidates[Math.min(attempt, candidates.length - 1)];
    return {
        src,
        alt: `${title} ${variant === 'poster' ? 'poster' : 'backdrop'}`,
        isFallback: src.startsWith('data:image'),
    };
};

export const formatRuntime = (runtime?: number): string =>
    runtime ? `${Math.floor(runtime / 60)}h ${runtime % 60}m` : 'Unknown runtime';

export const formatYear = (releaseDate?: string): string =>
    releaseDate?.split('-')[0] || 'Unscheduled';
