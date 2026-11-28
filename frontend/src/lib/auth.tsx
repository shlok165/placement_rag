import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from './api';

export type User = {
  id: number;
  email: string;
  full_name: string;
  role: 'student' | 'coordinator';
  consent_at: string | null;
  onboarded_at: string | null;
};

export function useUser() {
  return useQuery({
    queryKey: ['me'],
    queryFn: async () => {
      try {
        return await api<User>('/auth/me');
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    staleTime: 5 * 60_000,
  });
}

export function useLogin() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; password: string }) =>
      api<User>('/auth/login', { method: 'POST', body }),
    onSuccess: (user) => {
      client.clear();
      client.setQueryData(['me'], user);
    },
  });
}

export type SignInOptions = { demo: boolean; google: boolean };

/** Extra ways to sign in that this server offers: the shared demo account and Google. */
export function useSignInOptions() {
  return useQuery({
    queryKey: ['sign-in-options'],
    queryFn: () => api<SignInOptions>('/auth/options'),
    staleTime: Infinity,
  });
}

export function useDemoAvailable() {
  const { data, ...rest } = useSignInOptions();
  return { ...rest, data: data?.demo };
}

export function useDemoLogin() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api<User>('/auth/demo', { method: 'POST' }),
    onSuccess: (user) => {
      client.clear();
      client.setQueryData(['me'], user);
    },
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api<void>('/auth/logout', { method: 'POST' }),
    onSettled: () => {
      client.clear();
      client.setQueryData(['me'], null);
    },
  });
}

export function homePath(user: User): string {
  if (user.role === 'coordinator') return '/admin';
  return user.onboarded_at ? '/' : '/onboarding';
}
