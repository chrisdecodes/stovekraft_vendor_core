# implementing the function to match arch and avoid sdk coupling
import time

def paginate(
    next_token_param="NextToken",
    throttle_by_seconds=1,
    extras=None,
    next_token_only=False
):
    if extras is None:
        extras = {}

    def decorator(func):
        def wrapper(*args, **kwargs):
            while True:
                res = func(*args, **kwargs)

                yield res

                next_token = res.next_token
                if not next_token:
                    break

                time.sleep(throttle_by_seconds)

                if next_token_only:
                    kwargs = {next_token_param: next_token}
                else:
                    kwargs.update({next_token_param: next_token, **extras})

        return wrapper
    return decorator