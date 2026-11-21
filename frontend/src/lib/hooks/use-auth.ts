import { User, UserRole } from '../types';

export type { User };
export { UserRole };

export interface UserUpdate {
    email?: string;
    full_name?: string;
    role?: UserRole;
    is_active?: boolean;
}
