# pylint: disable=C,R,E1101
import torch
import torch.nn as nn


class SE3GroupNorm(nn.Module):
    def __init__(self, Rs, eps=1e-5, affine=True):
        '''
        :param Rs: list of tuple (multiplicity, dimension)
        '''
        super().__init__()

        self.Rs = [(m, d) for m, d in Rs if m * d > 0]

        self.eps = eps
        self.affine = affine

        if affine:
            self.weight = nn.Parameter(torch.ones(sum([m for m, d in Rs])))
            self.bias = nn.Parameter(torch.zeros(sum([m for m, d in Rs if d == 1])))
        else:
            self.register_parameter('weight', None)
            self.register_parameter('bias', None)

    def __repr__(self):
        return "{name} (Rs={Rs}, eps={eps}, affine={affine})".format(name=self.__class__.__name__, **self.__dict__)

    def forward(self, input):  # pylint: disable=W
        '''
        :param input: [batch, stacked feature, x, y, z]
        '''

        fields = []
        ix = 0
        iw = 0
        ib = 0
        for m, d in self.Rs:
            field = input[:, ix: ix + m * d]  # [batch, feature * repr, x, y, z]
            ix += m * d
            field = field.contiguous().view(input.size(0), m, d, -1)  # [batch, feature, repr, x * y * z]

            if d == 1:  # scalars
                field_mean = field.view(input.size(0), -1).mean(-1)  # [batch]
                field = field - field_mean.view(-1, 1, 1, 1)  # [batch, feature, repr, x * y * z]

            field_norm = torch.sum(field ** 2, dim=2)  # [batch, feature, x * y * z]
            field_norm = field_norm.view(input.size(0), -1).mean(-1)  # [batch]
            field_norm = (field_norm + self.eps).pow(-0.5).view(-1, 1, 1, 1)  # [batch, feature, repr, x * y * z]

            if self.affine:
                weight = self.weight[iw: iw + m]  # [feature]
                iw += m
                field_norm = field_norm * weight.view(1, -1, 1, 1)  # [batch, feature, repr, x * y * z]

            field = field * field_norm  # [batch, feature, repr, x * y * z]

            if self.affine and d == 1:  # scalars
                bias = self.bias[ib: ib + m]  # [feature]
                ib += m
                field = field + bias.view(1, -1, 1, 1)  # [batch, feature, repr, x * y * z]

            fields.append(field.view(input.size(0), m * d, *input.size()[2:]))

        assert ix == input.size(1)
        if self.affine:
            assert iw == self.weight.size(0)
            assert ib == self.bias.size(0)
        return torch.cat(fields, dim=1)  # [batch, stacked feature, x, y, z]


def test_groupnorm():
    bn = SE3GroupNorm([(3, 1), (4, 3), (1, 5)])

    x = torch.rand(16, 3 + 12 + 5, 10, 10, 10)

    y = bn(x)
    return y


from se3cnn.image.convolution import SE3Convolution


class SE3GNConvolution(torch.nn.Module):
    '''
    This class is the analog of SE3BNConvolution
    Unfortunately the optimization done in SE3BNConvolution
    cannot be ported for group normalization
    '''

    def __init__(self, Rs_in, Rs_out, size, eps=1e-5, Rs_gn=None, **kwargs):
        super().__init__()
        if Rs_gn is None:
            Rs_gn = [(m, 2 * l + 1) for m, l in Rs_in]
        self.gn = SE3GroupNorm(Rs_gn, eps=eps)
        self.conv = SE3Convolution(Rs_in=Rs_in, Rs_out=Rs_out, size=size, **kwargs)

    def forward(self, input):  # pylint: disable=W
        return self.conv(self.gn(input))


if __name__ == "__main__":
    test_groupnorm()
