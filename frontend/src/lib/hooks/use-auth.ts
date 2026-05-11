import { useAuthStore } from '@/stores/auth-store';
import { User, UserRole } from '../types';

export type { User };
export { UserRole };

export interface UserUpdate {
    email?: string;
    full_name?: string;
    role?: UserRole;
    is_active?: boolean;
}

export function useAuth() {
    const store = useAuthStore();
    return {
        user: store.user,
        isAuthenticated: store.isAuthenticated,
        isLoading: store.isLoading,
        login: store.login,
        logout: store.logout,
        checkAuth: store.checkAuth,
        hasRole: (allowedRoles: UserRole[]) => {
            if (!store.user) return false;
            return allowedRoles.includes(store.user.role);
        }
    };
}
