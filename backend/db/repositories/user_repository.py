from backend.db.client import supabase


class UserRepository:

    def create(self, user_data: dict):
        return (
            supabase
            .table("users")
            .insert(user_data)
            .execute()
        )

    def get_all(self):
        return (
            supabase
            .table("users")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )

    def get_by_id(self, user_id: str):
        return (
            supabase
            .table("users")
            .select("*")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )

    def update(self, user_id: str, user_data: dict):
        return (
            supabase
            .table("users")
            .update(user_data)
            .eq("id", user_id)
            .execute()
        )

    def delete(self, user_id: str):
        return (
            supabase
            .table("users")
            .delete()
            .eq("id", user_id)
            .execute()
        )