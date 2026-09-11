from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from backend.db.repositories.user_repository import UserRepository
from backend.db.schemas.user import UserCreate, UserResponse, UserUpdate

router = APIRouter(
    prefix="/users",
    tags=["Users"]
)

user_repository = UserRepository()


@router.post(
    "/",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_user(user: UserCreate):
    try:
        response = user_repository.create(user.model_dump())

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="User could not be created"
            )

        return response.data[0]

    except HTTPException:
        raise

    except Exception as e:
        error_message = str(e)

        if "duplicate key value" in error_message.lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists"
            )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_message
        )


@router.get(
    "/",
    response_model=list[UserResponse],
    status_code=status.HTTP_200_OK
)
async def get_users():
    try:
        response = user_repository.get_all()
        return response.data

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK
)
async def get_user(user_id: UUID):
    try:
        response = user_repository.get_by_id(str(user_id))

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        return response.data[0]

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK
)
async def update_user(user_id: UUID, user: UserUpdate):
    try:
        existing_user = user_repository.get_by_id(str(user_id))

        if not existing_user.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        update_data = user.model_dump(exclude_unset=True)

        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No update fields were provided"
            )

        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        response = user_repository.update(
            str(user_id),
            update_data
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="User could not be updated"
            )

        return response.data[0]

    except HTTPException:
        raise

    except Exception as e:
        error_message = str(e)

        if "duplicate key value" in error_message.lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists"
            )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_message
        )


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_200_OK
)
async def delete_user(user_id: UUID):
    try:
        existing_user = user_repository.get_by_id(str(user_id))

        if not existing_user.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        user_repository.delete(str(user_id))

        return {
            "message": "User deleted successfully",
            "user_id": str(user_id)
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )