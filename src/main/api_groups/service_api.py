from kubernetes.client import CoreV1Api


# Returns a list of services https://github.com/kubernetes-client/python/blob/master/kubernetes/docs/V1Service.md


def get_service_by_name(core_api_client: CoreV1Api, namespace, name):
    services = core_api_client.list_service_for_all_namespaces(watch=False)
    return list(filter(lambda service: service.metadata.name == name and service.metadata.namespace == namespace,
                       services.items))


def get_service_ip(service):
    return service.spec.cluster_ip


def get_service_ip_by_name(core_api_client: CoreV1Api, service_name, namespace):
    services = get_service_by_name(core_api_client, namespace, service_name)
    if len(services) == 0:
        return None
    else:
        return get_service_ip(services[0])
