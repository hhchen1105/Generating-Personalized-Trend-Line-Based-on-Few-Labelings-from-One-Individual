import os
import sys
import json
import logging
import random
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from tqdm import tqdm
from sklearn.model_selection import train_test_split

import torch
import torch.nn as nn
from torch.nn.modules.linear import Linear
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader

## 20 個 random variables
batch_size=200
lr = 0.005
epochs = 200
device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
Folder_PATH = "./mixer_multiple_full/"
FORMAT = '%(asctime)s %(levelname)s: %(message)s'

## Transform into tensor
class TensorData(Dataset):
    def __init__(self, fileNames):
        self.fileNames = fileNames
    def __len__(self):
        return len(self.fileNames)
    def __getitem__(self, index):
        file = self.fileNames[index]
        x=[]
        y=[]
        with open(file) as f:
            data = json.load(f)
            value = np.array(data["value"])
            trend = np.array(data["trend"])
            weights = np.array(data["weights"])
            x.append(np.vstack((value,trend)))
            y.append(weights)
        x = torch.tensor(np.array(x))
        x = x.view(2,1680)
        y = torch.tensor(np.array(y))
        y = y.view(3)
        return x, y

## Model
class ConvNet(nn.Module):
    def __init__(self):
        super(ConvNet, self).__init__()
        self.layer1 = nn.Sequential(
            nn.Conv1d(2, 16, kernel_size=3),
            nn.ReLU(),
            nn.Conv1d(16, 32, kernel_size=3),
            nn.ReLU(),
            nn.Conv1d(32, 32, kernel_size=3),
            nn.ReLU(),
            nn.Conv1d(32, 64, kernel_size=3),
            nn.ReLU(),
        )
        self.fc = nn.Sequential(
            nn.Linear(107008, 3),
            nn.BatchNorm1d(3)
        )

    def forward(self, x):
        out = self.layer1(x)
        out = out.reshape(out.size(0),-1)
        out = self.fc(out)
        out = nn.Softmax()(out)
        return out

def ReadFileItem(FolderPath):
    FileNameContainer=[]
    idx=0
    for fileName in os.listdir(FolderPath):
        FileNameContainer.append(os.path.join(FolderPath,fileName))
    return FileNameContainer

def TrainValidationTestSplit(FileContainer):
    # Test = random.sample(FileContainer, int(len(FileContainer)*0.2))
    # for file in Test:
    #     FileContainer.remove(file)
    Validation = random.sample(FileContainer, int(len(FileContainer)*0.2))
    for file in Validation:
        FileContainer.remove(file)
    return FileContainer, Validation#, Test

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, filename="Softmax_mul_full_Log.log", filemode='w', format=FORMAT)
    test_mse_std=[]
    test_mae_std=[]
    best_model_epoch_list=[]
    
    for time in tqdm(range(5)):
        ## Get Full dataset filename
        FileNames = ReadFileItem(Folder_PATH)
        logging.info("Success => Get file name")
        # train, validation, test = TrainValidationTestSplit(FileNames)
        train, validation = TrainValidationTestSplit(FileNames)
        logging.info("Train size: "+str(len(train)))
        logging.info("Validation size: "+str(len(validation)))
        # logging.info("Test size: "+str(len(test)))
        ## Trasform to tensor
        train_tensor = TensorData(train)
        validation_tensor = TensorData(validation)
        # test_tensor = TensorData(test)
        ## Transform to data loader
        train_loader = DataLoader(
                dataset=train_tensor,
                batch_size=batch_size,
                num_workers=8,
                shuffle=True
            )
        validation_loader = DataLoader(
            dataset=validation_tensor,
            batch_size=batch_size,
            num_workers=8,
            shuffle=True
        )
        # test_loader = DataLoader(
        #     dataset=test_tensor,
        #     batch_size=batch_size,
        #     num_workers=8
        # )
        model = ConvNet()
        model.to(device, dtype=torch.double)
        loss_mse = nn.MSELoss()
        loss_mae = nn.L1Loss()
        optimizer = torch.optim.Adamax(model.parameters(), lr=lr)
        best_validation = sys.maxsize
        best_model = model
        best_model_epoch=0
        ## Train
        mse_loss_list=[]
        mae_loss_list=[]
        validation_mse_loss=[]
        logging.info("Train")
        for epoch in tqdm(range(epochs)):
            ## Train
            model.train()
            current_epoch_mse_loss = 0.0
            current_epoch_mae_loss = 0.0
            for batch_idx, (data, target) in enumerate(train_loader):
                data, target = data.to(device), target.to(device)
                y_hat = model(data)
                target = target.to(dtype=float)
                loss = loss_mse(y_hat, target)
                current_epoch_mse_loss+=loss.item()
                loss_L1 = loss_mae(y_hat, target)
                current_epoch_mae_loss+=loss_L1.item()
                loss.backward()
                optimizer.step()
                optimizer.zero_grad()
            logging.info("Epoch_" + str(epoch) + "_mse_loss: " + str(current_epoch_mse_loss/len(train_loader)))

            mse_loss_list.append(current_epoch_mse_loss/len(train_loader))
            mae_loss_list.append(current_epoch_mae_loss/len(train_loader))
            ## Validation
            model.eval()
            validation_loss = 0.0
            with torch.no_grad():
                for batch_idx, (data, target) in enumerate(validation_loader):
                    data, target = data.to(device), target.to(device)
                    y_hat = model(data)
                    target = target.to(dtype=float)
                    loss = loss_mse(y_hat, target)
                    validation_loss+=loss.item()
            if validation_loss < best_validation:
                best_validation = validation_loss
                best_model = model
                best_model_epoch = epoch
            validation_mse_loss.append(validation_loss/len(validation_loader))
        try:
            torch.save(best_model.state_dict(),"Softmax_multipletrend_full_"+str(time))
            logging.info("Success => save model")
        except:
            logging.error("Failed => save model")
        # model.load_state_dict(torch.load("Classifier_softmax"))
        best_model_epoch_list.append(best_model_epoch)
        plt.plot(mse_loss_list, label='Train')
        plt.plot(validation_mse_loss, label='Validation')
        plt.savefig("Softmax_mul_full_train_mse_"+str(time)+".pdf")
        plt.close()

        ## Test
        # print("test")
        # test_mse = 0
        # test_mae = 0
        # count=0
        # model = best_model
        # f = open("Softmax_mul_full_test_"+str(time)+".txt", "w")
        # with torch.no_grad():
        #     for batch_idx, (data, target) in enumerate(test_loader):
        #         data, target = data.to(device), target.to(device)
        #         y_hat = model(data)
        #         test_mse += loss_mse(y_hat, target)
        #         test_mae += loss_mae(y_hat, target)
        #         for i in range(len(y_hat)):
        #             f.write("Target two param: " + str(target[i].cpu().detach().numpy()) + "\n")
        #             f.write("Predict two param: " + str(y_hat[i].cpu().detach().numpy()) + "\n")
        #             f.write("--------------------------------------\n")
        # test_mse_std.append(test_mse.cpu().detach().item() / len(test_loader))
        # test_mae_std.append(test_mae.cpu().detach().item() / len(test_loader))

    logging.info("best train model epoch: "+ str(best_model_epoch_list))
    # logging.info("test MSE: "+ str(test_mse_std))
    # logging.info("test MSE 樣本標準差: "+str(np.std(test_mse_std, ddof=1)))
    # logging.info("test MAE: "+ str(test_mae_std))
    # logging.info("test MAE 樣本標準差: "+str(np.std(test_mae_std, ddof=1)))
