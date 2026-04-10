import Link from 'next/link';
import { ArrowUpRight, Sparkles, Star } from 'lucide-react';

import type { Movie } from '@/api';
import MovieArtwork from '@/components/MovieArtwork';
import { cn, formatMatchScore, formatYear } from '@/utils';

interface PosterMosaicProps {
    movies: Movie[];
    className?: string;
    leadLabel?: string;
}

const pickShowcaseMovies = (movies: Movie[]): Movie[] => {
    const uniqueMovies = Array.from(
        new Map(movies.map((movie) => [movie.id, movie])).values(),
    );
    const withArtwork = uniqueMovies.filter((movie) => movie.poster_path || movie.backdrop_path);
    const fallback = uniqueMovies.filter((movie) => !movie.poster_path && !movie.backdrop_path);
    return [...withArtwork, ...fallback].slice(0, 5);
};

export default function PosterMosaic({
    movies,
    className,
    leadLabel = 'Poster Reel',
}: PosterMosaicProps) {
    const featuredMovies = pickShowcaseMovies(movies);
    const leadMovie = featuredMovies[0];
    const supportMovies = featuredMovies.slice(1, 5);

    if (!leadMovie) return null;

    const genres = Array.isArray(leadMovie.genres)
        ? leadMovie.genres.slice(0, 3)
        : typeof leadMovie.genres === 'string'
            ? leadMovie.genres.split(/[,|]/).map((g) => g.trim()).filter(Boolean).slice(0, 3)
            : [];
    const leadScore = leadMovie.hybrid_score && leadMovie.hybrid_score > 0
        ? leadMovie.hybrid_score / 100
        : leadMovie.score || leadMovie.vote_average / 10;

    return (
        <section className={cn('grid gap-4 xl:grid-cols-[minmax(0,1.12fr)_minmax(0,0.88fr)]', className)}>
            <Link href={`/movie/${leadMovie.id}`} className="group block">
                <article className="poster-card relative h-full overflow-hidden rounded-[2.2rem]">
                    <div className="relative min-h-[340px] sm:min-h-[440px]">
                        <MovieArtwork
                            movie={leadMovie}
                            variant="backdrop"
                            priority
                            sizes="(max-width: 1280px) 100vw, 56vw"
                            className="absolute inset-0"
                            imageClassName="object-cover transition duration-700 group-hover:scale-[1.03]"
                        />
                        <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(4,4,5,0.08),rgba(4,4,5,0.25)_25%,rgba(4,4,5,0.82)_72%,rgba(4,4,5,0.96))]" />
                        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(242,193,79,0.22),transparent_28%),radial-gradient(circle_at_10%_18%,rgba(160,71,71,0.16),transparent_22%)]" />

                        <div className="absolute inset-x-0 top-0 flex items-start justify-between gap-4 p-5 sm:p-6">
                            <div className="rounded-full border border-[#f2c14f]/28 bg-black/40 px-3 py-1 text-[0.68rem] uppercase tracking-[0.28em] text-[#f2c14f]">
                                {leadLabel}
                            </div>
                            <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-black/35 px-3 py-1 text-[0.68rem] uppercase tracking-[0.2em] text-[#efe6d5]">
                                <Sparkles className="h-3.5 w-3.5 text-[#f2c14f]" />
                                {formatMatchScore(leadScore)}
                            </div>
                        </div>

                        <div className="absolute inset-x-0 bottom-0 p-5 sm:p-7">
                            <div className="max-w-2xl rounded-[1.8rem] border border-white/10 bg-black/40 p-5 shadow-[0_18px_55px_rgba(0,0,0,0.28)] backdrop-blur-md sm:p-6">
                                <div className="flex items-center justify-between gap-4 text-[0.68rem] uppercase tracking-[0.28em] text-[#d8ccb8]">
                                    <span>{formatYear(leadMovie.release_date)}</span>
                                    <span className="inline-flex items-center gap-2">
                                        <Star className="h-3.5 w-3.5 fill-[#f2c14f] text-[#f2c14f]" />
                                        {leadMovie.vote_average > 0 ? leadMovie.vote_average.toFixed(1) : 'N/A'}
                                    </span>
                                </div>
                                <h3 className="mt-3 text-3xl font-semibold leading-tight text-[#f8f1e5] sm:text-4xl">
                                    {leadMovie.title}
                                </h3>
                                <p className="mt-3 max-w-xl text-sm leading-relaxed text-[#d8ccb8] sm:text-base">
                                    {leadMovie.overview || 'A lead selection pulled from the live catalog with full artwork and detail metadata.'}
                                </p>
                                <div className="mt-4 flex flex-wrap gap-2">
                                    {(genres.length > 0 ? genres : ['Editorial Selection']).map((genre) => (
                                        <span
                                            key={`${leadMovie.id}-${genre}`}
                                            className="rounded-full border border-white/10 bg-white/7 px-3 py-1 text-[0.68rem] uppercase tracking-[0.2em] text-[#f0e5d2]"
                                        >
                                            {genre}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </div>
                </article>
            </Link>

            <div className="grid grid-cols-2 gap-4">
                {supportMovies.map((movie) => (
                    <Link key={movie.id} href={`/movie/${movie.id}`} className="group block">
                        <article className="poster-card relative overflow-hidden rounded-[1.7rem]">
                            <div className="relative aspect-[0.84]">
                                <MovieArtwork
                                    movie={movie}
                                    variant="poster"
                                    sizes="(max-width: 768px) 50vw, 24vw"
                                    className="absolute inset-0"
                                    imageClassName="object-cover transition duration-700 group-hover:scale-[1.04]"
                                />
                                <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(6,6,8,0.08),rgba(6,6,8,0.18)_38%,rgba(6,6,8,0.88))]" />
                                <div className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-3 p-4">
                                    <div>
                                        <div className="text-[0.62rem] uppercase tracking-[0.28em] text-[#d8ccb8]">
                                            {formatYear(movie.release_date)}
                                        </div>
                                        <h4 className="mt-2 line-clamp-2 text-lg font-semibold leading-tight text-[#f8f1e5]">
                                            {movie.title}
                                        </h4>
                                    </div>
                                    <div className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-[#f2c14f]/30 bg-black/45 text-[#f2c14f] opacity-0 transition duration-300 group-hover:opacity-100">
                                        <ArrowUpRight className="h-4 w-4" />
                                    </div>
                                </div>
                            </div>
                        </article>
                    </Link>
                ))}
            </div>
        </section>
    );
}
