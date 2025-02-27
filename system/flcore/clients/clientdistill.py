from collections import defaultdict
import copy
import torch
import torch.nn as nn
import numpy as np
import time
from flcore.clients.clientbase import Client


class clientDistill(Client):
    def __init__(self, args, id, train_samples, test_samples, **kwargs):
        super().__init__(args, id, train_samples, test_samples, **kwargs)

        self.logits = None
        self.global_logits = None
        self.loss_mse = nn.MSELoss()

        self.lamda = args.lamda


    def train(self):
        trainloader = self.load_train_data()
        start_time = time.time()

        # self.model.to(self.device)
        self.model.train()

        max_local_steps = self.local_steps
        if self.train_slow:
            max_local_steps = np.random.randint(1, max_local_steps // 2)

        logits = defaultdict(list)
        for step in range(max_local_steps):
            for i, (x, y) in enumerate(trainloader):
                if type(x) == type([]):
                    x[0] = x[0].to(self.device)
                else:
                    x = x.to(self.device)
                y = y.to(self.device)
                if self.train_slow:
                    time.sleep(0.1 * np.abs(np.random.rand()))
                self.optimizer.zero_grad()
                output = self.model(x)
                loss = self.loss(output, y)

                if self.global_logits != None:
                    logit_new = torch.zeros_like(output)
                    for i, yy in enumerate(y):
                        y_c = yy.item()
                        logit_new[i, :] = self.global_logits[y_c].data
                    loss += self.loss_mse(logit_new, output) * self.lamda

                for i, yy in enumerate(y):
                    y_c = yy.item()
                    logits[y_c].append(output[i, :].detach().data)

                loss.backward()
                self.optimizer.step()

        # self.model.cpu()

        self.logits = agg_func(logits)

        if self.learning_rate_decay:
            self.learning_rate_scheduler.step()

        self.train_time_cost['num_rounds'] += 1
        self.train_time_cost['total_cost'] += time.time() - start_time


    def set_logits(self, global_logits):
        self.global_logits = copy.deepcopy(global_logits)

    def train_metrics(self):
        trainloader = self.load_train_data()
        # self.model = self.load_model('model')
        # self.model.to(self.device)
        self.model.eval()

        train_num = 0
        losses = 0
        with torch.no_grad():
            for x, y in trainloader:
                if type(x) == type([]):
                    x[0] = x[0].to(self.device)
                else:
                    x = x.to(self.device)
                y = y.to(self.device)
                output = self.model(x)
                loss = self.loss(output, y)

                if self.global_logits != None:
                    logit_new = torch.zeros_like(output)
                    for i, yy in enumerate(y):
                        y_c = yy.item()
                        logit_new[i, :] = self.global_logits[y_c].data
                    loss += self.loss_mse(logit_new, output) * self.lamda
                    
                train_num += y.shape[0]
                losses += loss.item() * y.shape[0]

        # self.model.cpu()
        # self.save_model(self.model, 'model')

        return losses, train_num


# https://github.com/yuetan031/fedlogit/blob/main/lib/utils.py#L205
def agg_func(logits):
    """
    Returns the average of the weights.
    """

    for [label, logit_list] in logits.items():
        if len(logit_list) > 1:
            logit = 0 * logit_list[0].data
            for i in logit_list:
                logit += i.data
            logits[label] = logit / len(logit_list)
        else:
            logits[label] = logit_list[0]

    return logits