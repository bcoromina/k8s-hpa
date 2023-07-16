from kubernetes.client import CustomObjectsApi


def get_usages_from_pod(custom_objects_api: CustomObjectsApi, pod_name, namespace):
    resource = custom_objects_api.list_namespaced_custom_object(group="metrics.k8s.io", version="v1beta1",
                                                                namespace=namespace, plural="pods")
    usage = {}
    for pod in resource["items"]:

        pn = pod["metadata"]["name"]
        labels = pod["metadata"]["labels"]
        if "role" in labels and labels["role"] == "web" and pn == pod_name:

            for c in pod["containers"]:
                if c["name"] == "web":  # container name 'web'
                    usage = c["usage"]
    return usage
