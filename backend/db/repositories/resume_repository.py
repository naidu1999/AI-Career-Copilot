from backend.db.client import supabase


class ResumeRepository:

    def create(self, resume_data: dict):
        return (
            supabase
            .table("resumes")
            .insert(resume_data)
            .execute()
        )

    def get_by_user_id(self, user_id: str):
        return (
            supabase
            .table("resumes")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )

    def get_by_id(self, resume_id: str):
        return (
            supabase
            .table("resumes")
            .select("*")
            .eq("id", resume_id)
            .limit(1)
            .execute()
        )