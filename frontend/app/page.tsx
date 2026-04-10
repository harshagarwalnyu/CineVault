import HomeExperience from '@/components/HomeExperience';
import { getMoviesByGenre, getTrendingMovies, getLatestMovies } from '@/server-api';

export const revalidate = 30;

export default async function Home() {
    const [trending, actionMovies, latestMovies] = await Promise.all([
        getTrendingMovies(18),
        getMoviesByGenre('Action'),
        getLatestMovies(12),
    ]);

    return (
        <HomeExperience
            initialTrending={trending}
            initialActionMovies={actionMovies}
            initialLatestMovies={latestMovies}
        />
    );
}
