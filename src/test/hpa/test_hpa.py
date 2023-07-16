import time

from main.hpa.hpa_main import scale_replicas, ScalerAction


class TestHpa:
    upper_cpu_thr = 0.7
    lower_cpu_thr = 0.4
    namespace = "my_namespace"
    min_replicas = 2
    max_replicas = 5
    loop_time = 90
    no_scale_period = 300

    def test_scale_up_on_high_cpu(self):
        requested_deployment_cpu = 100
        deployment_replicas = 3
        ready_replicas: list[tuple[str, str]] = dummy_pod_name_ip_pairs(deployment_replicas)
        total_cpu_usage = requested_deployment_cpu * len(ready_replicas)

        hpa_config = HpaConfigStub(self.min_replicas, self.max_replicas, self.upper_cpu_thr, self.lower_cpu_thr,
                                   self.loop_time, self.no_scale_period)
        cluster_actions = ClusterActionsStub(self.namespace, requested_deployment_cpu, deployment_replicas,
                                             ready_replicas, total_cpu_usage)
        action = scale_replicas(cluster_actions, hpa_config, None, 0)

        assert action == ScalerAction.SCALE_UP
        assert cluster_actions.get_replicas_set() == deployment_replicas + 1

    def test_do_nothing_between_thresholds(self):
        requested_deployment_cpu = 100
        deployment_replicas = 3
        ready_replicas: list[tuple[str, str]] = dummy_pod_name_ip_pairs(deployment_replicas)
        mid_range_threshold = (self.upper_cpu_thr + self.lower_cpu_thr) / 2
        total_cpu_usage = mid_range_threshold * requested_deployment_cpu * len(ready_replicas)
        action = self.run_hpa(deployment_replicas, self.loop_time, self.max_replicas, self.min_replicas, self.no_scale_period,
                              ready_replicas, requested_deployment_cpu, total_cpu_usage)

        assert action == ScalerAction.NOTHING

    def test_scale_down_on_low_cpu(self):
        requested_deployment_cpu = 100
        deployment_replicas = 3

        ready_replicas: list[tuple[str, str]] = [
            ("pod_a", "ip_a"),
            ("pod_b", "ip_b"),
            ("pod_c", "ip_c")
        ]

        custom_info = CustomInfoStub(
            {
                "ip_a": 3, # ip : num_datasets
                "ip_b": 0,
                "ip_c": 55
            }
        )

        total_cpu_usage = requested_deployment_cpu * (self.lower_cpu_thr / 2) * len(ready_replicas)
        hpa_config = HpaConfigStub(self.min_replicas, self.max_replicas, self.upper_cpu_thr, self.lower_cpu_thr,
                                   self.loop_time, self.no_scale_period)
        cluster_actions = ClusterActionsStub(self.namespace, requested_deployment_cpu, deployment_replicas,
                                             ready_replicas, total_cpu_usage)
        action = scale_replicas(cluster_actions, hpa_config, custom_info, 0)

        pods_to_delete = set(cluster_actions.get_pods_to_delete())

        assert action == ScalerAction.SCALE_DOWN
        assert cluster_actions.get_replicas_set() == deployment_replicas - 1

        assert len(pods_to_delete) == 1
        assert pods_to_delete == {"pod_b"}

    def test_do_nothing_pods_not_ready(self):
        requested_deployment_cpu = 100
        deployment_replicas = 3
        ready_replicas: list[tuple[str, str]] = dummy_pod_name_ip_pairs(deployment_replicas - 1)
        assert len(ready_replicas) == deployment_replicas - 1
        total_cpu_usage = requested_deployment_cpu * len(ready_replicas) #tendria que escalar

        action = self.run_hpa(deployment_replicas, self.loop_time, self.max_replicas, self.min_replicas,
                              self.no_scale_period, ready_replicas, requested_deployment_cpu, total_cpu_usage)

        assert action == ScalerAction.NOTHING

    def test_max_replicas(self):
        requested_deployment_cpu = 100
        deployment_replicas = 5
        ready_replicas: list[tuple[str, str]] = dummy_pod_name_ip_pairs(deployment_replicas)
        total_cpu_usage = requested_deployment_cpu * len(ready_replicas)

        action = self.run_hpa(deployment_replicas, self.loop_time, self.max_replicas, self.min_replicas,
                              self.no_scale_period, ready_replicas, requested_deployment_cpu, total_cpu_usage)

        assert action == ScalerAction.NOTHING

    def test_min_replicas(self):
        requested_deployment_cpu = 100
        deployment_replicas = 2

        ready_replicas: list[tuple[str, str]] = [
            ("pod_a", "ip_a"),
            ("pod_b", "ip_b"),
            ("pod_c", "ip_c")
        ]

        total_cpu_usage = requested_deployment_cpu * (self.lower_cpu_thr / 2) * len(ready_replicas)
        action = self.run_hpa(deployment_replicas, self.loop_time, self.max_replicas, self.min_replicas,
                              self.no_scale_period, ready_replicas, requested_deployment_cpu, total_cpu_usage)

        assert action == ScalerAction.NOTHING
    def test_no_scale_down_period(self):
        requested_deployment_cpu = 100
        deployment_replicas = 3

        ready_replicas: list[tuple[str, str]] = [
            ("pod_a", "ip_a"),
            ("pod_b", "ip_b"),
            ("pod_c", "ip_c")
        ]

        last_scale_up_time: float = time.time()

        total_cpu_usage = requested_deployment_cpu * (self.lower_cpu_thr / 2) * len(ready_replicas)
        action = self.run_hpa(deployment_replicas, self.loop_time, self.max_replicas, self.min_replicas,
                              self.no_scale_period, ready_replicas, requested_deployment_cpu,
                              total_cpu_usage, last_scale_up_time)


        assert action == ScalerAction.NOTHING


    def run_hpa(self,
                deployment_replicas,
                loop_time,
                max_replicas,
                min_replicas,
                no_scale_period,
                ready_replicas,
                requested_deployment_cpu,
                total_cpu_usage,
                last_scale_up: float = 0):
        hpa_config = HpaConfigStub(min_replicas, max_replicas, self.upper_cpu_thr, self.lower_cpu_thr, loop_time,
                                   no_scale_period)
        cluster_actions = ClusterActionsStub(self.namespace, requested_deployment_cpu, deployment_replicas,
                                             ready_replicas, total_cpu_usage)
        action = scale_replicas(cluster_actions, hpa_config, None, last_scale_up)
        return action


class CustomInfoStub:

    def __init__(self, pod_ip_datasets: dict[str, int]):
        self.pod_ip_datasets = pod_ip_datasets

    def get_pod_num_datasets(self, pod_ip):
        return self.pod_ip_datasets.get(pod_ip)


class HpaConfigStub:

    def __init__(self, min_r, max_r, upper_cpu_thr, lower_cpu_thr, loop_time, no_scale_period):
        self.mir = min_r
        self.mar = max_r
        self.uct = upper_cpu_thr  # 0.7
        self.lct = lower_cpu_thr  # 0.4
        self.lts = loop_time  # 90 segundos es lo que tarda en estar ready un pod de web
        self.nsdp = no_scale_period

    @property
    def no_scale_down_period_s(self):
        return self.nsdp

    @property
    def loop_time_s(self) -> float:
        return self.lts

    @property
    def lower_cpu_threshold(self) -> float:
        return self.lct

    @property
    def upper_cpu_threshold(self) -> float:
        return self.uct

    @property
    def min_replicas(self) -> int:
        return self.mir

    @property
    def max_replicas(self) -> int:
        return self.mar


def dummy_pod_name_ip_pairs(num):
    a = []
    for i in list(range(num)):
        a.append((str(i), str(i)))
    return a


class ClusterActionsStub:
    def __init__(self,
                 namespace,
                 requested_deployment_cpu,
                 deployment_replicas,
                 ready_replicas: list[tuple[str, str]],
                 total_cpu_usage: float
                 ):
        self.app = "my_app"
        self.role = "web"
        self.service_name = "web"
        self.main_container_name = "web"
        self.hpa_web = "web"
        self.deployment_web = "web"
        self.namespace = namespace
        self.requested_deployment_cpu = requested_deployment_cpu
        self.replicas_set = None
        self.deployment_replicas = deployment_replicas
        self.ready_replicas = ready_replicas
        self.total_cpu_usage = total_cpu_usage
        self.pods_to_delete = []

    def get_requested_deployment_cpu(self):
        return self.requested_deployment_cpu

    def get_replicas_set(self):
        return self.replicas_set

    def set_deployment_replicas(self, target_replicas):
        self.replicas_set = target_replicas

    def get_deployment_replicas(self):
        return self.deployment_replicas

    def get_name_ip_pairs(self) -> list[tuple[str, str]]:
        return self.ready_replicas

    def get_total_cpu_usage(self, name_ip_pairs: list[tuple[str, str]]) -> float:
        return self.total_cpu_usage

    def get_pods_to_delete(self):
        return self.pods_to_delete

    def annotate_pod_deletion_cost(self, name: str, cost: int) -> None:
        if cost == 0:
            self.pods_to_delete.append(name)
