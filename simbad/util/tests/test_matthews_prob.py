"""Test functions for simbad.util.matthews_prob"""

__author__ = "Adam Simpkin"
__date__ = "16 Aug 2017"

import os
import unittest
from simbad.util import matthews_prob

SIMBAD_ROOT = os.environ['SIMBAD_ROOT']


class Test(unittest.TestCase):
    """Unit test"""

    def test_solvent_content(self):
        """Test case for matthews_prob.SolventContent.calculate_from_file"""

        input_model = os.path.join(SIMBAD_ROOT, "test_data", "toxd.pdb")
        volume = 16522.4616729
        SC = matthews_prob.SolventContent(volume)
        data = SC.calculate_from_file(input_model)

        reference_data = 0.48960068050640637

        self.assertAlmostEqual(data, reference_data)

    def test_matthews_prob(self):
        """Test case for matthews_prob.MatthewsProbability.calculate_from_file"""

        input_model = os.path.join(SIMBAD_ROOT, "test_data", "toxd.pdb")
        volume = 16522.4616729
        MC = matthews_prob.MatthewsProbability(volume)
        data = MC.calculate_from_file(input_model)

        reference_data = (0.48960068050640637, 1)

        self.assertAlmostEqual(data[0], reference_data[0])
        self.assertAlmostEqual(data[1], reference_data[1])


if __name__ == "__main__":
    unittest.main()
