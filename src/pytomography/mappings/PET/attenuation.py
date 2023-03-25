from __future__ import annotations
import torch
import pytomography
from pytomography.utils.helper_functions import rotate_detector_z, pad_image
from pytomography.mappings import MapNet
from pytomography.metadata import ObjectMeta, ImageMeta

def get_prob_of_detection_matrix(CT: torch.Tensor, dx: float) -> torch.tensor: 
	return torch.exp(-torch.sum(CT * dx, axis=1)).unsqueeze(dim=1)

class PETAttenuationNet(MapNet):
    def __init__(self, CT: torch.Tensor, device: str = pytomography.device) -> None:
        super(PETAttenuationNet, self).__init__(device)
        self.CT = CT.to(device)
        
    def initialize_network(self, object_meta: ObjectMeta, image_meta: ImageMeta) -> None:
        self.object_meta = object_meta
        self.image_meta = image_meta
        self.norm_image = torch.zeros(self.image_meta.padded_shape).to(self.device)
        CT = pad_image(self.CT)
        for i, angle in enumerate(self.image_meta.angles):
            self.norm_image[i] = get_prob_of_detection_matrix(rotate_detector_z(CT, angle), self.object_meta.dx)
    
    @torch.no_grad()
    def forward(
		self,
		image: torch.Tensor,
		norm_constant: torch.Tensor | None = None,
        mode: str = 'forward_project'
	) -> torch.tensor:
        return image*self.norm_image.unsqueeze(dim=0)