import NextAuth from "next-auth"
import CredentialsProvider from "next-auth/providers/credentials"
import axios from "axios"

const { handlers } = NextAuth({
    secret: process.env.AUTH_SECRET,
    providers: [
        CredentialsProvider({
            name: "Credentials",
            credentials: {
                username: { label: "Username", type: "text" },
                password: { label: "Password", type: "password" }
            },
            async authorize(credentials) {
                if (!credentials?.username) return null;

                try {
                    const apiUrl = (
                        process.env.API_URL ||
                        process.env.NEXT_PUBLIC_API_URL ||
                        "http://127.0.0.1:8001"
                    ).replace(/\/$/, "");
                    const res = await axios.post(`${apiUrl}/users/login`, {
                        username: credentials.username,
                        password: credentials.password
                    });

                    if (res.data.success) {
                        return {
                            id: res.data.user.id.toString(),
                            name: res.data.user.username,
                            email: res.data.user.email
                        };
                    }
                    return null;
                } catch {
                    // If backend login fails, return null
                    return null
                }
            }
        })
    ],
    pages: {
        signIn: '/login',
    },
    session: {
        strategy: "jwt",
        maxAge: 86400, // 24 Hours
    },
    cookies: {
        sessionToken: {
            name: `next-auth.session-token`,
            options: {
                httpOnly: true,
                sameSite: 'strict',
                path: '/',
                secure: process.env.NODE_ENV === 'production'
            }
        }
    },
    callbacks: {
        async jwt({ token, user }: { token: any, user: any }) {
            if (user) {
                token.id = user.id;
            }
            return token;
        },
        async session({ session, token }: { session: any, token: any }) {
            if (session.user) {
                session.user.id = token.id as string;
            }
            return session;
        }
    }
})

export const { GET, POST } = handlers
