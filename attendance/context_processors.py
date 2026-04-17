from django.utils import timezone


def global_context(request):
    return {
        "today": timezone.localdate(),
    }

