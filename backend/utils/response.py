def success(data=None, message="Success"):

    return {
        "success": True,
        "message": message,
        "data": data,
        "error": None
    }


def failure(error, message="Failed"):

    return {
        "success": False,
        "message": message,
        "data": None,
        "error": error
    }