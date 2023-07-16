from kubernetes.client import AppsV1Api


def get_deployment_by_name(apps_api_client: AppsV1Api, deployment_name, namespace):
    deployments = apps_api_client.list_namespaced_deployment(namespace)
    return list(filter(lambda d: d.metadata.name == deployment_name, deployments.items))


def get_deployment_replicas(apps_api_client: AppsV1Api, deployment_name, namespace):
    deployments = get_deployment_by_name(apps_api_client, deployment_name, namespace)
    if len(deployments) != 1:
        return 0
    else:
        web_depoyment = deployments[0]
        return web_depoyment.spec.replicas


def set_deployment_replicas(apps_api_client: AppsV1Api, deployment_name, namespace, num_replicas):
    patch = [{'op': 'replace', 'path': '/spec/replicas', 'value': num_replicas}]
    apps_api_client.patch_namespaced_deployment_scale(deployment_name, namespace, patch)


def get_deployment_resource_requests(apps_api_client: AppsV1Api, deployment_name, namespace, container_name):
    deployments = get_deployment_by_name(apps_api_client, deployment_name, namespace)
    if len(deployments) != 1:
        return {"cpu": "0m"}
    else:
        web_deployment = deployments[0]
        containers = web_deployment.spec.template.spec.containers
        web_container = next(c for c in containers if c.name == container_name)
        return web_container.resources.requests