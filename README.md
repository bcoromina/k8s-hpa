# k8s-hpa
Config via the following environment varialbles: 

MIN_REPLICAS: Minimum replicas in low activity (CPU).
MAX_REPLICAS: Maximum replicas in high activity (CPU).
UPPER_CPU_THRESHOLD: Float from 0 to 1. Applied to the total requested CPU to calculate the threshold CPU to scale up.
LOWER_CPU_THRESHOLD: Float from 0 to 1. Applied to the total requested CPU to calculate the threshold CPU to scale down.
LOOP_TIME_S: Time between scale action evaluation. As a minimum it should be the amout of time that takes to a pod to be ready.
NO_SCALE_DOWN_PERIOD: Minimum time a pod will be alive. Used to prevent unstable situations.
