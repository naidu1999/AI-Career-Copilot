from backend.db.client import supabase


class ResumeSectionRepository:

    def create(self, section_data: dict):
        return (
            supabase
            .table("resume_sections")
            .insert(section_data)
            .execute()
        )

    def get_by_resume_id(self, resume_id: str):
        return (
            supabase
            .table("resume_sections")
            .select("*")
            .eq("resume_id", resume_id)
            .limit(1)
            .execute()
        )

    def update(self, resume_id: str, section_data: dict):
        return (
            supabase
            .table("resume_sections")
            .update(section_data)
            .eq("resume_id", resume_id)
            .execute()
        )