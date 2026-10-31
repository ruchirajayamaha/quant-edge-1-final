| Window | Model | Confidence | VaR (%) | VaR (USD) | ES (%) | ES (USD) | ES minus VaR (bps) | VaR minus Normal (bps) | ES minus Normal (bps) | Status | Region | Reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| recent_development_1260d | historical | 0.90 | 0.4291 | 42910.90 | 0.7013 | 70126.16 | 27.2153 | -5.9052 | 2.6197 | ok | N/A | N/A |
| recent_development_1260d | parametric_normal | 0.90 | 0.4882 | 48816.06 | 0.6751 | 67506.50 | 18.6904 | 0.0000 | 0.0000 | ok | N/A | N/A |
| recent_development_1260d | monte_carlo_normal | 0.90 | 0.4873 | 48727.99 | 0.6781 | 67808.78 | 19.0808 | -0.0881 | 0.3023 | ok | N/A | N/A |
| recent_development_1260d | evt_pot | 0.90 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | unavailable | N/A | confidence 0.9 < threshold_quantile 0.95: pure POT tail inference is unavailable in the loss body; the empirical-body/GPD-tail hybrid must be requested explicitly (estimate_evt_body_tail). |
| recent_development_1260d | evt_body_tail_hybrid | 0.90 | 0.4291 | 42910.90 | 0.7010 | 70101.98 | 27.1911 | -5.9052 | 2.5955 | ok | body | VaR lies in the empirical BODY (below 1 - p_u); it is not EVT extrapolation |
| recent_development_1260d | historical | 0.95 | 0.5927 | 59272.67 | 0.9061 | 90614.38 | 31.3417 | -3.8861 | 10.9591 | ok | N/A | N/A |
| recent_development_1260d | parametric_normal | 0.95 | 0.6316 | 63158.73 | 0.7966 | 79655.23 | 16.4965 | 0.0000 | 0.0000 | ok | N/A | N/A |
| recent_development_1260d | monte_carlo_normal | 0.95 | 0.6338 | 63384.50 | 0.8025 | 80249.91 | 16.8654 | 0.2258 | 0.5947 | ok | N/A | N/A |
| recent_development_1260d | evt_pot | 0.95 | 0.5927 | 59272.67 | 0.9057 | 90566.01 | 31.2933 | -3.8861 | 10.9108 | ok | threshold_boundary | N/A |
| recent_development_1260d | evt_body_tail_hybrid | 0.95 | 0.5927 | 59272.67 | 0.9057 | 90566.01 | 31.2933 | -3.8861 | 10.9108 | ok | threshold_boundary | N/A |
| recent_development_1260d | historical | 0.99 | 1.0414 | 104137.56 | 1.5018 | 150178.25 | 46.0407 | 14.0744 | 46.7371 | ok | N/A | N/A |
| recent_development_1260d | parametric_normal | 0.99 | 0.9006 | 90063.18 | 1.0344 | 103441.16 | 13.3780 | 0.0000 | 0.0000 | ok | N/A | N/A |
| recent_development_1260d | monte_carlo_normal | 0.99 | 0.9074 | 90737.47 | 1.0482 | 104815.52 | 14.0780 | 0.6743 | 1.3744 | ok | N/A | N/A |
| recent_development_1260d | evt_pot | 0.99 | 1.0629 | 106293.35 | 1.5130 | 151297.01 | 45.0037 | 16.2302 | 47.8559 | ok | tail | N/A |
| recent_development_1260d | evt_body_tail_hybrid | 0.99 | 1.0629 | 106293.35 | 1.5130 | 151297.01 | 45.0037 | 16.2302 | 47.8559 | ok | tail | N/A |
| full_development_3020d | historical | 0.90 | 0.5349 | 53488.25 | 0.9688 | 96884.80 | 43.3965 | -14.1064 | 3.2577 | ok | N/A | N/A |
| full_development_3020d | parametric_normal | 0.90 | 0.6759 | 67594.60 | 0.9363 | 93627.12 | 26.0325 | 0.0000 | 0.0000 | ok | N/A | N/A |
| full_development_3020d | monte_carlo_normal | 0.90 | 0.6851 | 68505.21 | 0.9431 | 94313.39 | 25.8082 | 0.9106 | 0.6863 | ok | N/A | N/A |
| full_development_3020d | evt_pot | 0.90 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | unavailable | N/A | confidence 0.9 < threshold_quantile 0.95: pure POT tail inference is unavailable in the loss body; the empirical-body/GPD-tail hybrid must be requested explicitly (estimate_evt_body_tail). |
| full_development_3020d | evt_body_tail_hybrid | 0.90 | 0.5349 | 53488.25 | 0.9704 | 97044.84 | 43.5566 | -14.1064 | 3.4177 | ok | body | VaR lies in the empirical BODY (below 1 - p_u); it is not EVT extrapolation |
| full_development_3020d | historical | 0.95 | 0.8181 | 81806.85 | 1.2704 | 127037.71 | 45.2309 | -5.7646 | 16.4895 | ok | N/A | N/A |
| full_development_3020d | parametric_normal | 0.95 | 0.8757 | 87571.44 | 1.1055 | 110548.19 | 22.9768 | 0.0000 | 0.0000 | ok | N/A | N/A |
| full_development_3020d | monte_carlo_normal | 0.95 | 0.8786 | 87859.25 | 1.1127 | 111268.69 | 23.4094 | 0.2878 | 0.7205 | ok | N/A | N/A |
| full_development_3020d | evt_pot | 0.95 | 0.8181 | 81806.85 | 1.2736 | 127357.79 | 45.5509 | -5.7646 | 16.8096 | ok | threshold_boundary | N/A |
| full_development_3020d | evt_body_tail_hybrid | 0.95 | 0.8181 | 81806.85 | 1.2736 | 127357.79 | 45.5509 | -5.7646 | 16.8096 | ok | threshold_boundary | N/A |
| full_development_3020d | historical | 0.99 | 1.4824 | 148244.03 | 2.1595 | 215949.02 | 67.7050 | 23.1994 | 72.2712 | ok | N/A | N/A |
| full_development_3020d | parametric_normal | 0.99 | 1.2504 | 125044.65 | 1.4368 | 143677.84 | 18.6332 | 0.0000 | 0.0000 | ok | N/A | N/A |
| full_development_3020d | monte_carlo_normal | 0.99 | 1.2646 | 126458.38 | 1.4420 | 144203.21 | 17.7448 | 1.4137 | 0.5254 | ok | N/A | N/A |
| full_development_3020d | evt_pot | 0.99 | 1.4915 | 149149.25 | 2.1844 | 218444.60 | 69.2953 | 24.1046 | 74.7668 | ok | tail | N/A |
| full_development_3020d | evt_body_tail_hybrid | 0.99 | 1.4915 | 149149.25 | 2.1844 | 218444.60 | 69.2953 | 24.1046 | 74.7668 | ok | tail | N/A |
